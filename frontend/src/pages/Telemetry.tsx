import React, { useState, useEffect } from "react";
import { PageTransition } from "../components/PageTransition";
import type { TelemetryRecord } from "../types/telemetry";
import { MOCK_TELEMETRY_SERIES } from "../services/mockData";
import { apiService } from "../services/api";

interface ChartPoint {
  x: number;
  y: number;
  label: string;
  val: number;
}

export const Telemetry: React.FC = () => {
  const [records, setRecords] = useState<TelemetryRecord[]>(MOCK_TELEMETRY_SERIES);
  const [selectedDevice, setSelectedDevice] = useState<string>("core-router-01");
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  useEffect(() => {
    apiService.getScenarioData("congestion").then((res) => {
      if (res.records && res.records.length > 0) {
        setRecords(res.records);
      }
    });
  }, []);

  const deviceList: string[] = Array.from(new Set(records.map((r: TelemetryRecord) => r.device_id)));
  const deviceData: TelemetryRecord[] = records.filter((r: TelemetryRecord) => r.device_id === selectedDevice);

  // Helper to draw clean D3/SVG line chart
  const renderLineChart = (
    title: string,
    metricKey: keyof TelemetryRecord,
    unit: string,
    threshold: number,
    higherIsWorse: boolean = true
  ) => {
    const width = 500;
    const height = 140;
    const padding = { top: 20, right: 20, bottom: 25, left: 40 };

    const values: number[] = deviceData.map((d: TelemetryRecord) => (d[metricKey] as number) || 0);
    const maxVal = Math.max(...values, threshold * 1.2, 1);
    const minVal = Math.min(...values, 0);

    const points: ChartPoint[] = values.map((val: number, idx: number) => {
      const x = padding.left + (idx / Math.max(1, values.length - 1)) * (width - padding.left - padding.right);
      const y = height - padding.bottom - ((val - minVal) / (maxVal - minVal)) * (height - padding.top - padding.bottom);
      return { x, y, label: (deviceData[idx].timestamp as string) || `t${idx}`, val };
    });

    const pathD = points.reduce((acc, pt, i) => `${acc} ${i === 0 ? "M" : "L"} ${pt.x} ${pt.y}`, "");

    // Threshold line Y
    const thresholdY =
      height - padding.bottom - ((threshold - minVal) / (maxVal - minVal)) * (height - padding.top - padding.bottom);

    // Is breaching?
    const hasBreached = values.some((v: number) => (higherIsWorse ? v >= threshold : v <= threshold));

    return (
      <div data-spot style={{ borderTop: "var(--hairline-ink)", paddingTop: "1.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
          <div>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6875rem", opacity: 0.5 }}>
              METRIC FAMILY
            </p>
            <h3 className="serif-subhead" style={{ fontSize: "1.125rem" }}>
              {title}
            </h3>
          </div>
          <div style={{ textAlign: "right" }}>
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.75rem",
                color: hasBreached ? "var(--teal)" : "var(--ink)",
                fontWeight: hasBreached ? 500 : 400,
              }}
            >
              {hoverIndex !== null && points[hoverIndex]
                ? `${points[hoverIndex].val} ${unit}`
                : `${values[values.length - 1] || 0} ${unit}`}
            </span>
          </div>
        </div>

        <svg
          viewBox={`0 0 ${width} ${height}`}
          style={{ width: "100%", height: "auto", overflow: "visible" }}
          onMouseLeave={() => setHoverIndex(null)}
        >
          {/* Baseline axis */}
          <line
            x1={padding.left}
            y1={height - padding.bottom}
            x2={width - padding.right}
            y2={height - padding.bottom}
            stroke="var(--ink-15)"
            strokeWidth="1"
          />

          {/* Threshold Dashed Hairline */}
          {thresholdY >= padding.top && thresholdY <= height - padding.bottom && (
            <g>
              <line
                x1={padding.left}
                y1={thresholdY}
                x2={width - padding.right}
                y2={thresholdY}
                stroke="var(--ink-40)"
                strokeWidth="1"
                strokeDasharray="3 3"
              />
              <text
                x={width - padding.right}
                y={thresholdY - 4}
                textAnchor="end"
                fill="var(--ink)"
                fontSize="9"
                fontFamily="var(--font-mono)"
                opacity="0.5"
              >
                Limit: {threshold} {unit}
              </text>
            </g>
          )}

          {/* Data Path: Electric Teal ONLY if breached, otherwise 1.5px Ink */}
          <path
            d={pathD}
            fill="none"
            stroke={hasBreached ? "var(--teal)" : "var(--ink)"}
            strokeWidth={hasBreached ? "1.8" : "1.2"}
          />

          {/* Points & Synchronized Hover Bar */}
          {points.map((pt, idx) => (
            <g key={idx} onMouseEnter={() => setHoverIndex(idx)}>
              <circle
                cx={pt.x}
                cy={pt.y}
                r={hoverIndex === idx ? "4" : "2"}
                fill="var(--ivory)"
                stroke={hasBreached ? "var(--teal)" : "var(--ink)"}
                strokeWidth="1.2"
              />
              {/* Invisible wide hit area */}
              <rect
                x={pt.x - 10}
                y={padding.top}
                width={20}
                height={height - padding.top - padding.bottom}
                fill="transparent"
                style={{ cursor: "crosshair" }}
              />
            </g>
          ))}

          {/* Synchronized Vertical Crosshair Line */}
          {hoverIndex !== null && points[hoverIndex] && (
            <line
              x1={points[hoverIndex].x}
              y1={padding.top}
              x2={points[hoverIndex].x}
              y2={height - padding.bottom}
              stroke="var(--ink-40)"
              strokeWidth="1"
              strokeDasharray="2 2"
            />
          )}
        </svg>
      </div>
    );
  };

  return (
    <PageTransition theme="ivory">
      <div style={{ padding: "clamp(3rem, 6vw, 6rem) var(--margin-gutter)" }}>
        {/* Header & Device Filter Dropdown */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-end",
            marginBottom: "4rem",
            borderBottom: "var(--solid-ink)",
            paddingBottom: "2rem",
          }}
        >
          <div>
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.75rem",
                letterSpacing: "0.08em",
                opacity: 0.5,
                marginBottom: "0.75rem",
              }}
            >
              TIME-SERIES STUDIO
            </p>
            <h1
              className="serif-headline"
              style={{
                fontSize: "clamp(2.4rem, 4vw, 3.8rem)",
              }}
            >
              Multi-Dimensional Telemetry
            </h1>
          </div>

          <div>
            <label
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.6875rem",
                opacity: 0.5,
                display: "block",
                marginBottom: "0.5rem",
              }}
            >
              TARGET DEVICE DOMAIN
            </label>
            <select
              value={selectedDevice}
              onChange={(e) => setSelectedDevice(e.target.value)}
              style={{
                padding: "0.5rem 1rem",
                border: "var(--hairline-ink)",
                backgroundColor: "transparent",
                color: "var(--ink)",
                fontFamily: "var(--font-mono)",
                fontSize: "0.8125rem",
                outline: "none",
                cursor: "pointer",
              }}
            >
              {deviceList.map((dev) => (
                <option key={dev} value={dev}>
                  {dev}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Four Synchronized Chart Families in 2x2 Editorial Layout */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "clamp(2.5rem, 5vw, 5rem)",
          }}
        >
          {/* Family 1: Transit Performance */}
          <div>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.4, marginBottom: "0.5rem" }}>
              01 / TRANSIT PERFORMANCE
            </p>
            {renderLineChart("Round-Trip Latency (RTT)", "latency_ms", "ms", 100.0, true)}
            <div style={{ marginTop: "2rem" }}>
              {renderLineChart("Packet Loss Ratio", "packet_loss_pct", "%", 2.0, true)}
            </div>
          </div>

          {/* Family 2: Interface & Capacity */}
          <div>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.4, marginBottom: "0.5rem" }}>
              02 / INTERFACE & CAPACITY
            </p>
            {renderLineChart("Bandwidth Utilization", "bandwidth_util_pct", "%", 80.0, true)}
            <div style={{ marginTop: "2rem" }}>
              {renderLineChart("Egress Throughput", "throughput_mbps", "Mbps", 800.0, false)}
            </div>
          </div>

          {/* Family 3: Hardware Health */}
          <div>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.4, marginBottom: "0.5rem" }}>
              03 / HARDWARE HEALTH
            </p>
            {renderLineChart("CPU Starvation", "cpu_util_pct", "%", 75.0, true)}
            <div style={{ marginTop: "2rem" }}>
              {renderLineChart("Hardware Queue Drops", "queue_drops", "pkts", 0, true)}
            </div>
          </div>

          {/* Family 4: Access Layer & RF */}
          <div>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", opacity: 0.4, marginBottom: "0.5rem" }}>
              04 / ACCESS LAYER & RESOLUTION
            </p>
            {renderLineChart("Wi-Fi Signal Strength (RSSI)", "wifi_rssi_dbm", "dBm", -75.0, false)}
            <div style={{ marginTop: "2rem" }}>
              {renderLineChart("Carrier Flapping Transitions", "interface_flapping_count", "trans", 2, true)}
            </div>
          </div>
        </div>
      </div>
    </PageTransition>
  );
};
