import { Card, CardContent, Divider, Grid, Stack, Typography } from "@mui/material";
import AirIcon from "@mui/icons-material/Air";
import BatteryChargingFullIcon from "@mui/icons-material/BatteryChargingFull";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import type { Config } from "../types";

interface BoundRowProps {
  icon: React.ReactNode;
  label: string;
  onTemp: number;
  offTemp: number;
  onColor: string;
}

function BoundRow({ icon, label, onTemp, offTemp, onColor }: BoundRowProps) {
  return (
    <Stack direction="row" alignItems="center" spacing={1.5} flexWrap="wrap">
      <Stack direction="row" alignItems="center" spacing={0.5} sx={{ minWidth: 90 }}>
        {icon}
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {label}
        </Typography>
      </Stack>

      <Stack direction="row" alignItems="center" spacing={0.5}>
        <ArrowUpwardIcon sx={{ fontSize: 14, color: onColor }} />
        <Typography variant="body2" sx={{ color: onColor, fontWeight: 700 }}>
          ON ≥ {onTemp}°C
        </Typography>
      </Stack>

      <Stack direction="row" alignItems="center" spacing={0.5}>
        <ArrowDownwardIcon sx={{ fontSize: 14, color: "primary.main" }} />
        <Typography variant="body2" sx={{ color: "primary.main", fontWeight: 700 }}>
          OFF ≤ {offTemp}°C
        </Typography>
      </Stack>
    </Stack>
  );
}

interface Props {
  config: Config;
}

export default function ConfigBounds({ config }: Props) {
  return (
    <>
      <Typography variant="overline" color="text.secondary" sx={{ pl: 0.5 }}>
        Configured Thresholds
      </Typography>
      <Card>
        <CardContent>
          <Grid container spacing={1.5}>
            <Grid item xs={12} sm={6}>
              <BoundRow
                icon={<AirIcon fontSize="small" sx={{ color: "warning.main" }} />}
                label="Fan"
                onTemp={config.fan_on_temp}
                offTemp={config.fan_off_temp}
                onColor="#ff9800"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <BoundRow
                icon={<BatteryChargingFullIcon fontSize="small" sx={{ color: "error.main" }} />}
                label="Battery"
                onTemp={config.bat_on_temp}
                offTemp={config.bat_off_temp}
                onColor="#f44336"
              />
            </Grid>
          </Grid>
          <Divider sx={{ my: 1.5 }} />
          <Typography variant="caption" color="text.disabled">
            Thresholds are set in <code>.env</code> — restart the backend to apply changes.
            Poll interval: {config.poll_interval}s
          </Typography>
        </CardContent>
      </Card>
    </>
  );
}
