import { Card, CardContent, Typography, Box, Tooltip, LinearProgress } from "@mui/material";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import type { SensorData, Config } from "../types";

interface Props {
  sensor: SensorData;
  config: Config;
}

function getTempColor(temp: number, config: Config): string {
  if (temp >= config.bat_off_temp) return "#f44336";       // red – battery threshold
  if (temp >= config.fan_on_temp) return "#ff9800";       // orange – fan threshold
  if (temp <= config.fan_off_temp - 5) return "#29b6f6"; // cool blue
  return "#4caf50";                                        // green – safe range
}

function barValue(temp: number, minDisplay = 10, maxDisplay = 60): number {
  return Math.min(100, Math.max(0, ((temp - minDisplay) / (maxDisplay - minDisplay)) * 100));
}

const MIN_DISPLAY = 10;
const MAX_DISPLAY = 60;

export default function SensorCard({ sensor, config }: Props) {
  const hasTemp = !sensor.error && sensor.temperature !== null;
  const temp = hasTemp ? (sensor.temperature as number) : null;
  const color = temp !== null ? getTempColor(temp, config) : "error.main";

  return (
    <Card sx={{ height: "100%", position: "relative", overflow: "visible" }}>
      {/* Colour accent bar at top */}
      {temp !== null && (
        <Box
          sx={{
            height: 3,
            width: "100%",
            bgcolor: color,
            borderRadius: "10px 10px 0 0",
            transition: "background-color 1s ease",
          }}
        />
      )}

      <CardContent sx={{ pb: "12px !important", pt: 1.5 }}>
        {/* Sensor name */}
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
          {sensor.name}
        </Typography>

        {/* Temperature value */}
        {temp !== null ? (
          <>
            <Typography
              variant="h4"
              sx={{
                fontWeight: 700,
                color,
                transition: "color 1s ease",
                lineHeight: 1.2,
                letterSpacing: "-0.5px",
              }}
            >
              {temp.toFixed(1)}
              <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 0.3 }}>
                °C
              </Typography>
            </Typography>

            {/* Progress bar relative to display range */}
            <Box sx={{ mt: 1 }}>
              <Tooltip title={`${MIN_DISPLAY}°C – ${MAX_DISPLAY}°C display range`} placement="bottom">
                <LinearProgress
                  variant="determinate"
                  value={barValue(temp, MIN_DISPLAY, MAX_DISPLAY)}
                  sx={{
                    height: 4,
                    borderRadius: 2,
                    bgcolor: "rgba(255,255,255,0.08)",
                    "& .MuiLinearProgress-bar": {
                      bgcolor: color,
                      transition: "transform 1s ease, background-color 1s ease",
                    },
                  }}
                />
              </Tooltip>
            </Box>
          </>
        ) : (
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.5 }}>
            <ErrorOutlineIcon color="error" fontSize="small" />
            <Typography variant="body2" color="error.main">
              No reading
            </Typography>
          </Box>
        )}

        {/* Sensor ID */}
        <Typography
          variant="caption"
          color="text.disabled"
          sx={{ display: "block", mt: 0.5, fontSize: "0.62rem", letterSpacing: 0 }}
        >
          {sensor.sensor_id}
        </Typography>
      </CardContent>
    </Card>
  );
}
