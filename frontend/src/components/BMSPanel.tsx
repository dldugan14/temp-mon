import React from "react";
import { Card, CardContent, Typography, Box, Grid, LinearProgress, Chip } from "@mui/material";
import BatteryFullIcon from "@mui/icons-material/BatteryFull";
import BatteryAlertIcon from "@mui/icons-material/BatteryAlert";
import BoltIcon from "@mui/icons-material/Bolt";
import ThermostatIcon from "@mui/icons-material/Thermostat";
import type { BMSData } from "../types";

interface Props {
  bms: BMSData;
}

function getSOCColor(soc: number): string {
  if (soc >= 80) return "#4caf50";  // green
  if (soc >= 50) return "#ff9800";  // orange
  if (soc >= 20) return "#ff5722";  // deep orange
  return "#f44336";                 // red
}

function getCurrentColor(current: number): string {
  if (current > 0) return "#2196f3";  // blue (charging)
  if (current < -10) return "#ff9800"; // orange (high discharge)
  return "#4caf50";                    // green (idle/low discharge)
}

export default function BMSPanel({ bms }: Props) {
  if (bms.error) {
    return (
      <Card>
        <CardContent>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
            <BatteryAlertIcon color="error" />
            <Typography variant="h6">Battery Management System</Typography>
          </Box>
          <Typography color="error.main">
            {bms.error_message || "BMS connection error or disabled"}
          </Typography>
        </CardContent>
      </Card>
    );
  }

  const socColor = getSOCColor(bms.soc);
  const currentColor = getCurrentColor(bms.pack_current);
  const isCharging = bms.pack_current > 0;
  const minCell = Math.min(...bms.cell_voltages);
  const maxCell = Math.max(...bms.cell_voltages);
  const cellDelta = maxCell - minCell;

  return (
    <Card>
      <CardContent>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
          <BatteryFullIcon sx={{ color: socColor }} />
          <Typography variant="h6">Battery Management System</Typography>
          {isCharging && (
            <Chip
              label="Charging"
              size="small"
              color="primary"
              icon={<BoltIcon />}
              sx={{ ml: "auto" }}
            />
          )}
        </Box>

        {/* Pack-level stats */}
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={6} sm={3}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Pack Voltage
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: "#29b6f6" }}>
                {bms.pack_voltage.toFixed(2)}
                <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 0.5 }}>
                  V
                </Typography>
              </Typography>
            </Box>
          </Grid>

          <Grid item xs={6} sm={3}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Current
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: currentColor }}>
                {bms.pack_current.toFixed(2)}
                <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 0.5 }}>
                  A
                </Typography>
              </Typography>
            </Box>
          </Grid>

          <Grid item xs={6} sm={3}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                State of Charge
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: socColor }}>
                {bms.soc.toFixed(1)}
                <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 0.5 }}>
                  %
                </Typography>
              </Typography>
              <LinearProgress
                variant="determinate"
                value={bms.soc}
                sx={{
                  mt: 0.5,
                  height: 6,
                  borderRadius: 3,
                  bgcolor: "rgba(255,255,255,0.08)",
                  "& .MuiLinearProgress-bar": {
                    bgcolor: socColor,
                    transition: "transform 1s ease, background-color 1s ease",
                  },
                }}
              />
            </Box>
          </Grid>

          <Grid item xs={6} sm={3}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                Power
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: currentColor }}>
                {(bms.pack_voltage * bms.pack_current / 1000).toFixed(2)}
                <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 0.5 }}>
                  kW
                </Typography>
              </Typography>
            </Box>
          </Grid>
        </Grid>

        {/* Cell voltages */}
        {bms.cell_voltages.length > 0 && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
              Cell Voltages ({bms.cell_voltages.length} cells) | Δ: {(cellDelta * 1000).toFixed(0)}mV
            </Typography>
            <Grid container spacing={0.5}>
              {bms.cell_voltages.map((voltage, idx) => {
                const isMin = voltage === minCell;
                const isMax = voltage === maxCell;
                const color = isMin ? "#ff9800" : isMax ? "#4caf50" : "text.secondary";
                
                return (
                  <Grid item xs={3} sm={2} md={1.5} key={idx}>
                    <Box
                      sx={{
                        p: 0.5,
                        textAlign: "center",
                        borderRadius: 1,
                        bgcolor: "rgba(255,255,255,0.03)",
                        border: isMin || isMax ? `1px solid ${color}` : "1px solid transparent",
                      }}
                    >
                      <Typography variant="caption" color="text.disabled">
                        {idx + 1}
                      </Typography>
                      <Typography
                        variant="body2"
                        sx={{ fontWeight: isMin || isMax ? 700 : 400, color }}
                      >
                        {voltage.toFixed(3)}V
                      </Typography>
                    </Box>
                  </Grid>
                );
              })}
            </Grid>
          </Box>
        )}

        {/* Temperatures */}
        {bms.temperatures.length > 0 && (
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
              <ThermostatIcon sx={{ fontSize: 14, verticalAlign: "middle", mr: 0.5 }} />
              BMS Temperatures
            </Typography>
            <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
              {bms.temperatures.map((temp, idx) => (
                <Chip
                  key={idx}
                  label={`${idx + 1}: ${temp.toFixed(1)}°C`}
                  size="small"
                  sx={{
                    bgcolor: temp > 40 ? "rgba(255,152,0,0.2)" : "rgba(255,255,255,0.08)",
                    color: temp > 40 ? "#ff9800" : "text.secondary",
                  }}
                />
              ))}
            </Box>
          </Box>
        )}
      </CardContent>
    </Card>
  );
}
