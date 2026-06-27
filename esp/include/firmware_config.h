#pragma once

#include <stdint.h>

#include "secrets.h"

#ifndef FM_DEVICE_NAME
#error "FM_DEVICE_NAME is not defined. Define it in secret.h"
#endif

#ifndef FM_WIFI_SSID_1
#error "FM_WIFI_SSID_1 is not defined. Define it in secrets.h"
#endif

#ifndef FM_WIFI_PASSWORD_1
#error "FM_WIFI_PASSWORD_1 is not defined. Define it in secrets.h"
#endif

#ifndef FM_WIFI_SSID_2
#define FM_WIFI_SSID_2 ""
#endif
#ifndef FM_WIFI_PASSWORD_2
#define FM_WIFI_PASSWORD_2 ""
#endif

#ifndef FM_WIFI_SSID_3
#define FM_WIFI_SSID_3 ""
#endif
#ifndef FM_WIFI_PASSWORD_3
#define FM_WIFI_PASSWORD_3 ""
#endif

#ifndef FM_API_BASE_URL
#error "FM_API_BASE_URL is not defined. Define it in secret.h"
#endif

#ifndef FM_DEVICE_TOKEN
#error "FM_DEVICE_TOKEN is not defined. Define it in secret.h"
#endif

#ifndef FM_WAIT_COMMAND_PATH
#define FM_WAIT_COMMAND_PATH "/api/device/wait-command"
#endif

#ifndef FM_COMMAND_RESULT_PATH
#define FM_COMMAND_RESULT_PATH "/api/device/command-result"
#endif

#ifndef FM_RELAY_PIN
#define FM_RELAY_PIN 0
#endif

#ifndef FM_LED_PIN
#define FM_LED_PIN FM_RELAY_PIN
#endif

#ifndef FM_RELAY_ACTIVE_HIGH
#define FM_RELAY_ACTIVE_HIGH 1
#endif

#ifndef FM_MAX_RELAY_PULSE_MS
#define FM_MAX_RELAY_PULSE_MS 3000
#endif

#ifndef FM_DEFAULT_POLL_TIMEOUT_MS
#define FM_DEFAULT_POLL_TIMEOUT_MS 60000
#endif

#ifndef FM_DEFAULT_HTTP_TIMEOUT_MS
#define FM_DEFAULT_HTTP_TIMEOUT_MS 70000
#endif

#ifndef FM_TLS_CERT_FINGERPRINT
#define FM_TLS_CERT_FINGERPRINT ""
#endif

#ifndef FM_WIFI_CONNECT_TIMEOUT_MS
#define FM_WIFI_CONNECT_TIMEOUT_MS 30000
#endif

#ifndef FM_RECONNECT_JITTER_MIN_MS
#define FM_RECONNECT_JITTER_MIN_MS 100
#endif

#ifndef FM_RECONNECT_JITTER_MAX_MS
#define FM_RECONNECT_JITTER_MAX_MS 500
#endif

#ifndef FM_OTA_HOSTNAME
#define FM_OTA_HOSTNAME FM_DEVICE_NAME
#endif

#ifndef FM_OTA_PASSWORD
#error "FM_OTA_PASSWORD is not defined. Define it in secret.h"
#endif

#ifndef FM_NTP_SERVER_1
#define FM_NTP_SERVER_1 "pool.ntp.org"
#endif

#ifndef FM_NTP_SERVER_2
#define FM_NTP_SERVER_2 "time.nist.gov"
#endif

#ifndef FM_NTP_SERVER_3
#define FM_NTP_SERVER_3 "time.google.com"
#endif

namespace cfg
{

    static constexpr const char *kDeviceName = FM_DEVICE_NAME;
    static constexpr const char *kApiBaseUrl = FM_API_BASE_URL;

    struct WifiNetwork
    {
        const char *ssid;
        const char *password;
    };

    static constexpr WifiNetwork kWifiNetworks[] = {
        {FM_WIFI_SSID_1, FM_WIFI_PASSWORD_1},
        {FM_WIFI_SSID_2, FM_WIFI_PASSWORD_2},
        {FM_WIFI_SSID_3, FM_WIFI_PASSWORD_3},
    };
    static constexpr uint8_t kWifiNetworkCount = 3;
    static constexpr const char *kDeviceToken = FM_DEVICE_TOKEN;

    static constexpr const char *kWaitCommandPath = FM_WAIT_COMMAND_PATH;
    static constexpr const char *kCommandResultPath = FM_COMMAND_RESULT_PATH;

    static constexpr uint8_t kRelayPin = FM_RELAY_PIN;
    static constexpr uint8_t kLedPin = FM_LED_PIN;
    static constexpr bool kRelayActiveHigh = FM_RELAY_ACTIVE_HIGH != 0;
    static constexpr uint32_t kMaxRelayPulseMs = FM_MAX_RELAY_PULSE_MS;

    static constexpr uint32_t kPollTimeoutMs = FM_DEFAULT_POLL_TIMEOUT_MS;
    static constexpr uint32_t kHttpTimeoutMs = FM_DEFAULT_HTTP_TIMEOUT_MS;

    static constexpr const char *kTlsCertFingerprint = FM_TLS_CERT_FINGERPRINT;

    static constexpr uint32_t kWifiConnectTimeoutMs = FM_WIFI_CONNECT_TIMEOUT_MS;
    static constexpr uint32_t kReconnectJitterMinMs = FM_RECONNECT_JITTER_MIN_MS;
    static constexpr uint32_t kReconnectJitterMaxMs = FM_RECONNECT_JITTER_MAX_MS;

    static constexpr const char *kOtaHostname = FM_OTA_HOSTNAME;
    static constexpr const char *kOtaPassword = FM_OTA_PASSWORD;

    static constexpr const char *kNtpServer1 = FM_NTP_SERVER_1;
    static constexpr const char *kNtpServer2 = FM_NTP_SERVER_2;
    static constexpr const char *kNtpServer3 = FM_NTP_SERVER_3;

} // namespace cfg
