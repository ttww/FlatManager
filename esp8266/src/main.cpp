#include <Arduino.h>

#include <ArduinoJson.h>
#include <ESP8266HTTPClient.h>
#include <ESP8266WiFi.h>
#include <ESP8266mDNS.h>
#include <WiFiClientSecureBearSSL.h>
#include <ArduinoOTA.h>
#include <time.h>

#include "firmware_config.h"

namespace
{

    enum class PollResult
    {
        kNoCommand,
        kProcessed,
        kTransientError,
        kAuthError,
    };

    bool g_ota_initialized = false;
    bool g_time_synced = false;
    uint8_t g_backoff_index = 0;

    constexpr uint32_t kBackoffScheduleMs[] = {1000, 2000, 5000, 10000, 30000};

    uint32_t next_backoff_delay_ms()
    {
        const uint32_t delay_ms = kBackoffScheduleMs[g_backoff_index];
        constexpr size_t kBackoffScheduleSize = sizeof(kBackoffScheduleMs) / sizeof(kBackoffScheduleMs[0]);
        if (static_cast<size_t>(g_backoff_index + 1) < kBackoffScheduleSize)
        {
            g_backoff_index++;
        }
        return delay_ms;
    }

    void reset_backoff() { g_backoff_index = 0; }

    void service_background()
    {
        if (g_ota_initialized)
        {
            ArduinoOTA.handle();
        }
        ESP.wdtFeed();
        yield();
    }

    void safe_delay_ms(uint32_t delay_ms)
    {
        const uint32_t start = millis();
        while (millis() - start < delay_ms)
        {
            service_background();
            delay(10);
        }
    }

    void set_relay_state(bool on)
    {
        const bool pin_high = cfg::kRelayActiveHigh ? on : !on;
        digitalWrite(cfg::kRelayPin, pin_high ? HIGH : LOW);
    }

    void init_relay_gpio()
    {
        pinMode(cfg::kRelayPin, OUTPUT);
        set_relay_state(false);
    }

    String make_authorization_header()
    {
        String header = "Bearer ";
        header += cfg::kDeviceToken;
        return header;
    }

    String build_url(const char *path)
    {
        String url = cfg::kApiBaseUrl;
        url += path;
        return url;
    }

    bool has_tls_fingerprint() { return strlen(cfg::kTlsCertFingerprint) > 0; }

    uint16_t http_timeout_ms()
    {
        return cfg::kHttpTimeoutMs > 65000 ? 65000 : static_cast<uint16_t>(cfg::kHttpTimeoutMs);
    }

    std::unique_ptr<BearSSL::WiFiClientSecure> make_secure_client()
    {
        if (!has_tls_fingerprint())
        {
            Serial.println("TLS fingerprint missing. Refusing insecure connection.");
            return nullptr;
        }

        auto client = std::make_unique<BearSSL::WiFiClientSecure>();
        client->setTimeout(cfg::kHttpTimeoutMs / 1000);
        client->setFingerprint(cfg::kTlsCertFingerprint);
        return client;
    }

    void initialize_ota_once()
    {
        if (g_ota_initialized || WiFi.status() != WL_CONNECTED)
        {
            return;
        }

        ArduinoOTA.setHostname(cfg::kOtaHostname);
        if (strlen(cfg::kOtaPassword) > 0)
        {
            ArduinoOTA.setPassword(cfg::kOtaPassword);
        }

        ArduinoOTA.onStart([]()
                           { Serial.println("OTA start"); });
        ArduinoOTA.onEnd([]()
                         { Serial.println("OTA done"); });
        ArduinoOTA.onError([](ota_error_t error)
                           { Serial.printf("OTA error: %u\n", static_cast<unsigned>(error)); });

        ArduinoOTA.begin();
        g_ota_initialized = true;
        Serial.println("OTA initialized");
    }

    bool connect_wifi()
    {
        if (WiFi.status() == WL_CONNECTED)
        {
            return true;
        }

        WiFi.mode(WIFI_STA);
        WiFi.begin(cfg::kWifiSsid, cfg::kWifiPassword);
        Serial.printf("Connecting Wi-Fi SSID: %s\n", cfg::kWifiSsid);

        const uint32_t start = millis();
        while (WiFi.status() != WL_CONNECTED)
        {
            service_background();
            delay(200);

            if (millis() - start > cfg::kWifiConnectTimeoutMs)
            {
                Serial.println("Wi-Fi connect timeout");
                return false;
            }
        }

        Serial.printf("Wi-Fi connected. IP: %s\n", WiFi.localIP().toString().c_str());
        initialize_ota_once();
        return true;
    }

    bool sync_time_if_needed()
    {
        if (g_time_synced)
        {
            return true;
        }

        configTime(0, 0, cfg::kNtpServer1, cfg::kNtpServer2, cfg::kNtpServer3);
        Serial.println("Waiting for NTP time sync...");

        const uint32_t start = millis();
        while (true)
        {
            const time_t now = time(nullptr);
            if (now > 1700000000)
            {
                g_time_synced = true;
                Serial.println("Time synchronized");
                return true;
            }

            service_background();
            delay(200);

            if (millis() - start > 15000)
            {
                Serial.println("NTP sync timeout");
                return false;
            }
        }
    }

    bool format_current_utc_iso8601(char *out, size_t out_len)
    {
        const time_t now = time(nullptr);
        if (now <= 0)
        {
            return false;
        }

        struct tm tm_utc;
        gmtime_r(&now, &tm_utc);
        const size_t written = strftime(out, out_len, "%Y-%m-%dT%H:%M:%SZ", &tm_utc);
        return written > 0;
    }

    bool is_expired_iso8601_utc(const char *expires_at)
    {
        if (expires_at == nullptr || strlen(expires_at) < 20)
        {
            return true;
        }
        if (!g_time_synced)
        {
            return true;
        }

        char now_iso[32] = {0};
        if (!format_current_utc_iso8601(now_iso, sizeof(now_iso)))
        {
            return true;
        }

        return strcmp(now_iso, expires_at) > 0;
    }

    uint32_t clamp_duration_ms(uint32_t requested_ms)
    {
        if (requested_ms == 0)
        {
            return 1;
        }
        if (requested_ms > cfg::kMaxRelayPulseMs)
        {
            return cfg::kMaxRelayPulseMs;
        }
        return requested_ms;
    }

    bool post_command_result(int command_id, const char *status_value, const String &message)
    {
        auto client = make_secure_client();
        if (!client)
        {
            return false;
        }

        HTTPClient https;
        if (!https.begin(*client, build_url(cfg::kCommandResultPath)))
        {
            Serial.println("Failed to begin command-result request");
            return false;
        }

        https.setTimeout(http_timeout_ms());
        https.addHeader("Content-Type", "application/json");
        https.addHeader("Authorization", make_authorization_header());

        StaticJsonDocument<256> payload;
        payload["command_id"] = command_id;
        payload["status"] = status_value;
        payload["message"] = message;

        String body;
        serializeJson(payload, body);
        const int code = https.POST(body);
        if (code < 200 || code >= 300)
        {
            Serial.printf("Command-result POST failed: %d\n", code);
            https.end();
            return false;
        }

        https.end();
        return true;
    }

    bool pulse_relay_and_report(int command_id, uint32_t duration_ms)
    {
        const uint32_t safe_duration_ms = clamp_duration_ms(duration_ms);
        Serial.printf("Relay pulse %lu ms\n", static_cast<unsigned long>(safe_duration_ms));

        set_relay_state(true);
        safe_delay_ms(safe_duration_ms);
        set_relay_state(false);

        String msg = "Relay switched for ";
        msg += safe_duration_ms;
        msg += " ms";

        return post_command_result(command_id, "done", msg);
    }

    PollResult process_wait_command_response(const String &body)
    {
        StaticJsonDocument<512> doc;
        const DeserializationError err = deserializeJson(doc, body);
        if (err)
        {
            Serial.printf("JSON parse error: %s\n", err.c_str());
            return PollResult::kTransientError;
        }

        const char *command = doc["command"] | "none";
        if (strcmp(command, "none") == 0)
        {
            const uint32_t jitter = random(cfg::kReconnectJitterMinMs, cfg::kReconnectJitterMaxMs + 1);
            safe_delay_ms(jitter);
            return PollResult::kNoCommand;
        }

        const int command_id = doc["command_id"] | -1;
        if (strcmp(command, "open") != 0 || command_id < 0)
        {
            if (command_id >= 0)
            {
                post_command_result(command_id, "ignored", "Unsupported command");
            }
            return PollResult::kProcessed;
        }

        const char *expires_at = doc["expires_at"] | "";
        if (is_expired_iso8601_utc(expires_at))
        {
            post_command_result(command_id, "expired", "Command expired before execution");
            return PollResult::kProcessed;
        }

        const uint32_t requested_duration = doc["duration_ms"] | cfg::kMaxRelayPulseMs;
        if (!pulse_relay_and_report(command_id, requested_duration))
        {
            post_command_result(command_id, "failed", "Relay execution done but report failed");
        }

        return PollResult::kProcessed;
    }

    PollResult wait_for_command_once()
    {
        auto client = make_secure_client();
        if (!client)
        {
            return PollResult::kAuthError;
        }

        HTTPClient https;
        if (!https.begin(*client, build_url(cfg::kWaitCommandPath)))
        {
            Serial.println("Failed to begin wait-command request");
            return PollResult::kTransientError;
        }

        https.setTimeout(http_timeout_ms());
        https.addHeader("Authorization", make_authorization_header());

        const int code = https.GET();
        if (code == HTTP_CODE_UNAUTHORIZED || code == HTTP_CODE_FORBIDDEN)
        {
            Serial.printf("Auth error on wait-command: %d\n", code);
            https.end();
            return PollResult::kAuthError;
        }

        if (code != HTTP_CODE_OK)
        {
            Serial.printf("wait-command HTTP status: %d\n", code);
            https.end();
            return PollResult::kTransientError;
        }

        const String body = https.getString();
        https.end();
        return process_wait_command_response(body);
    }

    void print_boot_configuration()
    {
        Serial.println();
        Serial.println("FlatManager ESP8266 boot");
        Serial.printf("Device: %s\n", cfg::kDeviceName);
        Serial.printf("Relay pin: %u\n", cfg::kRelayPin);
        Serial.printf("Relay active high: %s\n", cfg::kRelayActiveHigh ? "true" : "false");
        Serial.printf("Max relay pulse ms: %lu\n", static_cast<unsigned long>(cfg::kMaxRelayPulseMs));
        Serial.printf("Poll timeout ms: %lu\n", static_cast<unsigned long>(cfg::kPollTimeoutMs));
        Serial.printf("HTTP timeout ms: %lu\n", static_cast<unsigned long>(cfg::kHttpTimeoutMs));
        Serial.printf("OTA hostname: %s\n", cfg::kOtaHostname);
        Serial.printf("Wi-Fi timeout ms: %lu\n", static_cast<unsigned long>(cfg::kWifiConnectTimeoutMs));
    }

} // namespace

void setup()
{
    Serial.begin(115200);
    delay(300);
    randomSeed(micros());
    ESP.wdtEnable(8000);
    init_relay_gpio();
    print_boot_configuration();
}

void loop()
{
    service_background();

    if (!connect_wifi())
    {
        const uint32_t delay_ms = next_backoff_delay_ms();
        Serial.printf("Wi-Fi reconnect backoff: %lu ms\n", static_cast<unsigned long>(delay_ms));
        safe_delay_ms(delay_ms);
        return;
    }

    sync_time_if_needed();

    const PollResult result = wait_for_command_once();
    if (result == PollResult::kNoCommand || result == PollResult::kProcessed)
    {
        reset_backoff();
        return;
    }

    const uint32_t delay_ms = result == PollResult::kAuthError ? 30000 : next_backoff_delay_ms();
    Serial.printf("Network/auth retry backoff: %lu ms\n", static_cast<unsigned long>(delay_ms));
    safe_delay_ms(delay_ms);
}
