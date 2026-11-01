#!/bin/sh

if [ "${1-}" = "--codex-refresh" ]; then
    printf 'refresh\n' >> "$LANE_BENCH_FAKE_REFRESH_LOG"
    printf '%s\n' "${USAGE_OPTIMIZER_CODEX_TIMEOUT-unset}" >> "$LANE_BENCH_FAKE_REFRESH_ENV_LOG"
    if [ -n "${LANE_BENCH_FAKE_STATUS_AFTER_REFRESH_FLAG-}" ]; then
        : > "$LANE_BENCH_FAKE_STATUS_AFTER_REFRESH_FLAG"
    fi
    exit 0
fi

if [ "${1-}" = "--no-agy" ] && [ "${2-}" = "--json" ]; then
    if [ -f "${LANE_BENCH_FAKE_STATUS_AFTER_REFRESH_FLAG-}" ]; then
        printf '%s\n' "$LANE_BENCH_FAKE_STATUS_AFTER_REFRESH_VALUE"
        exit 0
    fi
    index=0
    if [ -f "$LANE_BENCH_FAKE_STATUS_INDEX" ]; then
        index=$(cat "$LANE_BENCH_FAKE_STATUS_INDEX")
    fi
    index=$((index + 1))
    printf '%s\n' "$index" > "$LANE_BENCH_FAKE_STATUS_INDEX"
    reading=$(sed -n "${index}p" "$LANE_BENCH_FAKE_STATUS_SEQUENCE")
    if [ -z "$reading" ]; then
        reading=$(tail -n 1 "$LANE_BENCH_FAKE_STATUS_SEQUENCE")
    fi
    printf '%s\n' "$reading"
    exit 0
fi

exit 2
