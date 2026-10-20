// MS-CAN sniffer — 2011 Ford Fusion body bus (125 kbps, OBD2 pins 3/11).
//
// Listen-only: the TWAI controller never transmits or ACKs, so this cannot
// disturb the car's buses. Every received frame is printed with a millisecond
// timestamp, which is all you need for the sniff-diff-replay workflow:
//
//   1. Flash, open a serial monitor at 115200, ignition ON.
//   2. Save ~10 s of traffic = baseline log.
//   3. Press ONE climate button (e.g. A/C), save ~10 s = action log.
//   4. Diff the two logs: new/changed IDs and bytes are your button's message.
//
// Config: CAN_BITRATE_KBPS 125 = MS-CAN body bus (pins 3/11).
//         Set to 500 to sniff the HS-CAN powertrain bus (pins 6/14) instead.

#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_timer.h"
#include <inttypes.h>
#include "driver/twai.h"

// ---- configuration ----
#define TWAI_TX_GPIO        19      // J4 pad 7 (unused electrically in listen-only)
#define TWAI_RX_GPIO        20      // J4 pad 8 -> transceiver RXD
#define CAN_BITRATE_KBPS    125     // MS-CAN = 125 ; HS-CAN = 500
#define STATS_INTERVAL_MS   5000

#define MAX_IDS 256

static uint32_t seen_ids[MAX_IDS];
static int seen_count = 0;
static uint32_t total_frames = 0;
static uint32_t interval_frames = 0;

// Returns true the first time an ID is seen.
static bool note_id(uint32_t id)
{
    for (int i = 0; i < seen_count; i++) {
        if (seen_ids[i] == id) {
            return false;
        }
    }
    if (seen_count < MAX_IDS) {
        seen_ids[seen_count++] = id;
    }
    return true;
}

void app_main(void)
{
    printf("\n=== ESP32 MS-CAN sniffer ===\n");
    printf("bitrate: %d kbps | TWAI TX=%d RX=%d | mode: LISTEN ONLY (never transmits)\n",
           CAN_BITRATE_KBPS, TWAI_TX_GPIO, TWAI_RX_GPIO);
    printf("Wire: OBD2 pin 3 -> transceiver CANH, pin 11 -> CANL\n");
    printf("Serial monitor at 115200. Ignition ON = bus alive.\n\n");

    twai_general_config_t g_config =
        TWAI_GENERAL_CONFIG_DEFAULT(TWAI_TX_GPIO, TWAI_RX_GPIO, TWAI_MODE_LISTEN_ONLY);

#if CAN_BITRATE_KBPS == 125
    twai_timing_config_t t_config = TWAI_TIMING_CONFIG_125KBITS();
#elif CAN_BITRATE_KBPS == 500
    twai_timing_config_t t_config = TWAI_TIMING_CONFIG_500KBITS();
#else
#error "Unsupported CAN_BITRATE_KBPS (use 125 or 500)"
#endif

    twai_filter_config_t f_config = TWAI_FILTER_CONFIG_ACCEPT_ALL();

    ESP_ERROR_CHECK(twai_driver_install(&g_config, &t_config, &f_config));
    ESP_ERROR_CHECK(twai_start());
    ESP_ERROR_CHECK(twai_reconfigure_alerts(
        TWAI_ALERT_RX_DATA | TWAI_ALERT_ERR_PASS | TWAI_ALERT_BUS_ERROR, NULL));

    printf("TWAI started, listening...\n\n");

    int64_t last_stats = esp_timer_get_time();
    int64_t last_hint = last_stats;
    twai_message_t rx;
    uint32_t alerts;

    while (1) {
        if (twai_receive(&rx, pdMS_TO_TICKS(100)) == ESP_OK) {
            total_frames++;
            interval_frames++;
            int64_t ms = esp_timer_get_time() / 1000;
            bool is_new = note_id(rx.identifier);
            bool extd = (rx.flags & TWAI_MSG_FLAG_EXTD) != 0;
            bool rtr = (rx.flags & TWAI_MSG_FLAG_RTR) != 0;

            if (extd) {
                printf("[%" PRId64 "ms]%s ID:0x%08" PRIx32 "(ext) DLC:%d", ms, is_new ? " NEW" : "",
                       rx.identifier, rx.data_length_code);
            } else {
                printf("[%" PRId64 "ms]%s ID:0x%03" PRIx32 " DLC:%d", ms, is_new ? " NEW" : "",
                       rx.identifier, rx.data_length_code);
            }
            if (rtr) {
                printf(" RTR\n");
            } else {
                for (int i = 0; i < rx.data_length_code; i++) {
                    printf(" %02X", rx.data[i]);
                }
                printf("\n");
            }
            last_hint = esp_timer_get_time();
        }

        if (twai_read_alerts(&alerts, 0) == ESP_OK) {
            if (alerts & TWAI_ALERT_BUS_ERROR) {
                printf("[warn] bus error - check CANH/CANL wiring and termination\n");
            }
            if (alerts & TWAI_ALERT_ERR_PASS) {
                printf("[warn] error-passive - bus noisy or wrong bitrate?\n");
            }
        }

        int64_t now = esp_timer_get_time();
        if (now - last_stats > (int64_t)STATS_INTERVAL_MS * 1000) {
            uint32_t fps = interval_frames / (STATS_INTERVAL_MS / 1000);
            printf("--- stats: %" PRIu32 " frames total, %d unique IDs, ~%" PRIu32 " fps ---\n",
                   total_frames, seen_count, fps);
            interval_frames = 0;
            last_stats = now;
        }
        if (total_frames == 0 && now - last_hint > 15000000LL) {
            printf("[hint] no frames yet - ignition ON? CANH/CANL on the right pins? "
                   "try the 60-ohm check between OBD2 pins 3 and 11 (car off)\n");
            last_hint = now;
        }
    }
}
