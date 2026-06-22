#include <Arduino.h>

#include <ArduinoJson.h>
#include <ArduinoOTA.h>
#include <HTTPClient.h>
#include <time.h>
#include <memory>

#if defined(ESP8266)
#include <ESP8266WiFi.h>
#include <ESP8266mDNS.h>
#include <WiFiClientSecureBearSSL.h>
#elif defined(ESP32)
#include <WiFi.h>
#include <ESPmDNS.h>
#include <WiFiClientSecure.h>
#else
#error "Unsupported platform"
#endif

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

    void feed_watchdog()
    {
#if defined(ESP8266)
        ESP.wdtFeed();
#else
        yield();
#endif
    }

    void enable_watchdog()
    {
#if defined(ESP8266)
        ESP.wdtEnable(8000);
#endif
    }

    void set_wifi_hostname(const char *hostname)
    {
#if defined(ESP8266)
        WiFi.hostname(hostname);
#elif defined(ESP32)
        WiFi.setHostname(hostname);
#endif
    }

    // constexpr uint32_t kBackoffScheduleMs[] = {1000, 2000, 5000, 10000, 30000};
    constexpr uint32_t kBackoffScheduleMs[] = {1000, 1000, 1000, 1000, 1000};

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

    const char *wifi_status_name(wl_status_t status)
    {
        switch (status)
        {
        case WL_NO_SHIELD:
            return "WL_NO_SHIELD";
        case WL_IDLE_STATUS:
            return "WL_IDLE_STATUS";
        case WL_NO_SSID_AVAIL:
            return "WL_NO_SSID_AVAIL";
        case WL_SCAN_COMPLETED:
            return "WL_SCAN_COMPLETED";
        case WL_CONNECTED:
            return "WL_CONNECTED";
        case WL_CONNECT_FAILED:
            return "WL_CONNECT_FAILED";
        case WL_CONNECTION_LOST:
            return "WL_CONNECTION_LOST";
        case WL_DISCONNECTED:
            return "WL_DISCONNECTED";
        default:
            return "WL_UNKNOWN";
        }
    }

    const char *poll_result_name(PollResult result)
    {
        switch (result)
        {
        case PollResult::kNoCommand:
            return "no_command";
        case PollResult::kProcessed:
            return "processed";
        case PollResult::kTransientError:
            return "transient_error";
        case PollResult::kAuthError:
            return "auth_error";
        default:
            return "unknown";
        }
    }

    void log_wifi_status()
    {
        const String ssid = WiFi.SSID();
        const String ip = WiFi.localIP().toString();
        const String gateway = WiFi.gatewayIP().toString();
        Serial.printf(
            "Wi-Fi status=%s ssid=%s rssi=%d ip=%s gateway=%s\n",
            wifi_status_name(WiFi.status()),
            ssid.c_str(),
            WiFi.RSSI(),
            ip.c_str(),
            gateway.c_str());
    }

    void service_background()
    {
        if (g_ota_initialized)
        {
            ArduinoOTA.handle();
        }
        feed_watchdog();
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

    bool url_is_https(const String &url)
    {
        return url.startsWith("https://");
    }

    bool has_tls_fingerprint() { return strlen(cfg::kTlsCertFingerprint) > 0; }

    std::unique_ptr<WiFiClient> make_http_client(const String &url)
    {
        if (url_is_https(url))
        {
#if defined(ESP8266)
            if (!has_tls_fingerprint())
            {
                Serial.println("TLS fingerprint missing. Refusing HTTPS connection.");
                return nullptr;
            }

            auto client = std::make_unique<BearSSL::WiFiClientSecure>();
            client->setTimeout(cfg::kHttpTimeoutMs / 1000);
            client->setFingerprint(cfg::kTlsCertFingerprint);
            return client;
#elif defined(ESP32)
            auto client = std::make_unique<WiFiClientSecure>();
            client->setTimeout(cfg::kHttpTimeoutMs / 1000);
            client->setInsecure();
            Serial.println("HTTPS certificate validation disabled on ESP32. Use a CA certificate for production.");
            return client;
#endif
        }

        if (!url.startsWith("http://"))
        {
            Serial.printf("Unsupported API base URL scheme: %s\n", url.c_str());
            return nullptr;
        }

        auto client = std::make_unique<WiFiClient>();
        client->setTimeout(cfg::kHttpTimeoutMs / 1000);
        return client;
    }

    String format_connected_endpoint(HTTPClient &http)
    {
        WiFiClient *stream = http.getStreamPtr();
        if (stream == nullptr)
        {
            return String("unknown");
        }

        const IPAddress remote_ip = stream->remoteIP();
        const uint16_t remote_port = stream->remotePort();
        if (remote_port == 0)
        {
            return String("unknown");
        }

        String endpoint = remote_ip.toString();
        endpoint += ':';
        endpoint += remote_port;
        return endpoint;
    }

    uint16_t http_timeout_ms()
    {
        return cfg::kHttpTimeoutMs > 65000 ? 65000 : static_cast<uint16_t>(cfg::kHttpTimeoutMs);
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

        WiFi.persistent(false);
        WiFi.mode(WIFI_STA);
        set_wifi_hostname(cfg::kDeviceName);
        WiFi.setAutoReconnect(true);
        WiFi.begin(cfg::kWifiSsid, cfg::kWifiPassword);
        Serial.printf("Connecting Wi-Fi ssid=%s hostname=%s\n", cfg::kWifiSsid, cfg::kDeviceName);

        const uint32_t start = millis();
        uint32_t last_log_at = 0;
        while (WiFi.status() != WL_CONNECTED)
        {
            service_background();
            delay(200);

            const uint32_t elapsed = millis() - start;
            if (elapsed - last_log_at >= 2000)
            {
                last_log_at = elapsed;
                Serial.printf(
                    "Waiting for Wi-Fi... status=%s elapsed=%lu ms\n",
                    wifi_status_name(WiFi.status()),
                    static_cast<unsigned long>(elapsed));
            }

            if (elapsed > cfg::kWifiConnectTimeoutMs)
            {
                Serial.printf(
                    "Wi-Fi connect timeout after %lu ms (status=%s)\n",
                    static_cast<unsigned long>(elapsed),
                    wifi_status_name(WiFi.status()));
                return false;
            }
        }

        Serial.println("Wi-Fi connected");
        log_wifi_status();
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
        Serial.printf(
            "Waiting for NTP time sync via %s, %s, %s\n",
            cfg::kNtpServer1,
            cfg::kNtpServer2,
            cfg::kNtpServer3);

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
            Serial.printf(
                "Relay duration clamped from %lu to %lu ms\n",
                static_cast<unsigned long>(requested_ms),
                static_cast<unsigned long>(cfg::kMaxRelayPulseMs));
            return cfg::kMaxRelayPulseMs;
        }
        return requested_ms;
    }

    bool post_command_result(int command_id, const char *status_value, const String &message)
    {
        const String target_url = build_url(cfg::kCommandResultPath);
        auto client = make_http_client(target_url);
        if (!client)
        {
            return false;
        }

        HTTPClient https;
        if (!https.begin(*client, target_url))
        {
            Serial.printf("Failed to begin command-result request target=%s\n", target_url.c_str());
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
        Serial.printf(
            "Relay pulse command_id=%d duration_ms=%lu\n",
            command_id,
            static_cast<unsigned long>(safe_duration_ms));

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
            Serial.println("No command available");
            const uint32_t jitter = random(cfg::kReconnectJitterMinMs, cfg::kReconnectJitterMaxMs + 1);
            safe_delay_ms(jitter);
            return PollResult::kNoCommand;
        }

        const int command_id = doc["command_id"] | -1;
        Serial.printf("Received command=%s command_id=%d\n", command, command_id);
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
            Serial.printf("Command expired command_id=%d expires_at=%s\n", command_id, expires_at);
            post_command_result(command_id, "expired", "Command expired before execution");
            return PollResult::kProcessed;
        }

        const uint32_t requested_duration = doc["duration_ms"] | cfg::kMaxRelayPulseMs;
        Serial.printf(
            "Open command accepted command_id=%d requested_duration_ms=%lu expires_at=%s\n",
            command_id,
            static_cast<unsigned long>(requested_duration),
            expires_at);
        if (!pulse_relay_and_report(command_id, requested_duration))
        {
            post_command_result(command_id, "failed", "Relay execution done but report failed");
        }

        return PollResult::kProcessed;
    }

    PollResult wait_for_command_once()
    {
        const String target_url = build_url(cfg::kWaitCommandPath);
        auto client = make_http_client(target_url);
        if (!client)
        {
            return PollResult::kAuthError;
        }

        HTTPClient https;
        if (!https.begin(*client, target_url))
        {
            Serial.printf("Failed to begin wait-command request target=%s\n", target_url.c_str());
            return PollResult::kTransientError;
        }

        https.setTimeout(http_timeout_ms());
        https.addHeader("Authorization", make_authorization_header());

        const int code = https.GET();
        const String endpoint = format_connected_endpoint(https);
        if (code == HTTP_CODE_UNAUTHORIZED || code == HTTP_CODE_FORBIDDEN)
        {
            Serial.printf(
                "Auth error on wait-command: %d target=%s remote=%s\n",
                code,
                target_url.c_str(),
                endpoint.c_str());
            https.end();
            return PollResult::kAuthError;
        }

        if (code != HTTP_CODE_OK)
        {
            Serial.printf(
                "wait-command HTTP status: %d target=%s remote=%s\n",
                code,
                target_url.c_str(),
                endpoint.c_str());
            https.end();
            return PollResult::kTransientError;
        }

        const String body = https.getString();
        Serial.printf(
            "wait-command HTTP status: %d target=%s remote=%s response_bytes=%u\n",
            code,
            target_url.c_str(),
            endpoint.c_str(),
            static_cast<unsigned>(body.length()));
        https.end();
        return process_wait_command_response(body);
    }

    void print_boot_configuration()
    {
        Serial.println();
#if defined(ESP8266)
        Serial.println("FlatManager ESP8266 boot");
#elif defined(ESP32)
        Serial.println("FlatManager ESP32 boot");
#endif
        Serial.printf("Device: %s\n", cfg::kDeviceName);
        Serial.printf("API base: %s\n", cfg::kApiBaseUrl);
        Serial.printf("Wi-Fi SSID: %s\n", cfg::kWifiSsid);
        Serial.printf("Relay pin: %u\n", cfg::kRelayPin);
        Serial.printf("Relay active high: %s\n", cfg::kRelayActiveHigh ? "true" : "false");
        Serial.printf("Max relay pulse ms: %lu\n", static_cast<unsigned long>(cfg::kMaxRelayPulseMs));
        Serial.printf("Poll timeout ms: %lu\n", static_cast<unsigned long>(cfg::kPollTimeoutMs));
        Serial.printf("HTTP timeout ms: %lu\n", static_cast<unsigned long>(cfg::kHttpTimeoutMs));
        Serial.printf("OTA hostname: %s\n", cfg::kOtaHostname);
        Serial.printf("Wi-Fi timeout ms: %lu\n", static_cast<unsigned long>(cfg::kWifiConnectTimeoutMs));
    }

    void print_reset_info()
    {
#if defined(ESP8266)
        Serial.printf("Reset reason: %s\n", ESP.getResetReason().c_str());
        Serial.printf("Reset info: %s\n", ESP.getResetInfo().c_str());
#elif defined(ESP32)
        Serial.printf("Reset reason: %d\n", static_cast<int>(esp_reset_reason()));
#endif
    }

} // namespace

void setup()
{
    Serial.begin(115200);
    Serial.setDebugOutput(true);
    delay(2000);
    Serial.println();
#if defined(ESP8266)
    Serial.println("FlatManager ESP8266 starting up...");
#elif defined(ESP32)
    Serial.println("FlatManager ESP32 starting up...");
#endif
    print_reset_info();
    delay(300);

    randomSeed(micros());

    Serial.println("Boot stage: random seed done");

    enable_watchdog();
    Serial.println("Boot stage: watchdog enabled");
    init_relay_gpio();
    Serial.println("Boot stage: relay GPIO initialized");
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
    Serial.printf("Poll result: %s\n", poll_result_name(result));
    if (result == PollResult::kNoCommand || result == PollResult::kProcessed)
    {
        reset_backoff();
        return;
    }

    const uint32_t delay_ms = result == PollResult::kAuthError ? 30000 : next_backoff_delay_ms();
    Serial.printf("Network/auth retry backoff: %lu ms\n", static_cast<unsigned long>(delay_ms));
    safe_delay_ms(delay_ms);
}
