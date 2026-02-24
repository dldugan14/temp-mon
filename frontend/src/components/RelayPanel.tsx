import {
  Box,
  Card,
  CardContent,
  Chip,
  Grid,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import AirIcon from "@mui/icons-material/Air";
import BatteryChargingFullIcon from "@mui/icons-material/BatteryChargingFull";
import PowerSettingsNewIcon from "@mui/icons-material/PowerSettingsNew";
import AutoModeIcon from "@mui/icons-material/AutoMode";
import PowerOffIcon from "@mui/icons-material/PowerOff";
import { useState } from "react";
import { setRelayOverride, clearRelayOverride } from "../hooks/useSystemState";
import type { RelayData } from "../types";

interface RelayCardProps {
  relay: RelayData;
  label: string;
  icon: React.ReactNode;
}

function RelayCard({ relay, label, icon }: RelayCardProps) {
  const [busy, setBusy] = useState(false);

  const handleOverride = async (on: boolean) => {
    setBusy(true);
    try {
      await setRelayOverride(relay.name, on);
    } finally {
      setBusy(false);
    }
  };

  const handleAuto = async () => {
    setBusy(true);
    try {
      await clearRelayOverride(relay.name);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1.5} mb={1.5}>
          <Box sx={{ color: relay.state ? "warning.main" : "text.disabled" }}>{icon}</Box>
          <Box sx={{ flexGrow: 1 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600, lineHeight: 1.2 }}>
              {label}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              GPIO {relay.pin}
            </Typography>
          </Box>

          {/* State badge */}
          <Chip
            label={relay.state ? "ON" : "OFF"}
            size="small"
            color={relay.state ? "warning" : "default"}
            sx={{ fontWeight: 700, minWidth: 48 }}
          />

          {/* Auto / Manual badge */}
          <Chip
            label={relay.is_overridden ? "MANUAL" : "AUTO"}
            size="small"
            variant="outlined"
            color={relay.is_overridden ? "secondary" : "default"}
          />
        </Stack>

        {/* Control buttons */}
        <Stack direction="row" spacing={1}>
          <Tooltip title="Force ON">
            <span>
              <IconButton
                size="small"
                color="warning"
                disabled={busy || (relay.state && relay.is_overridden)}
                onClick={() => handleOverride(true)}
                sx={{ border: "1px solid", borderColor: "warning.main", borderRadius: 1.5 }}
              >
                <PowerSettingsNewIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>

          <Tooltip title="Force OFF">
            <span>
              <IconButton
                size="small"
                color="error"
                disabled={busy || (!relay.state && relay.is_overridden)}
                onClick={() => handleOverride(false)}
                sx={{ border: "1px solid", borderColor: "error.main", borderRadius: 1.5 }}
              >
                <PowerOffIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>

          <Tooltip title="Return to auto control">
            <span>
              <IconButton
                size="small"
                color="primary"
                disabled={busy || !relay.is_overridden}
                onClick={handleAuto}
                sx={{ border: "1px solid", borderColor: relay.is_overridden ? "primary.main" : "divider", borderRadius: 1.5 }}
              >
                <AutoModeIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
      </CardContent>
    </Card>
  );
}

interface Props {
  relays: { fan: RelayData; battery: RelayData };
}

export default function RelayPanel({ relays }: Props) {
  return (
    <>
      <Typography variant="overline" color="text.secondary" sx={{ pl: 0.5 }}>
        Relay Control
      </Typography>
      <Grid container spacing={1.5}>
        <Grid item xs={12} sm={6}>
          <RelayCard
            relay={relays.fan}
            label="Fan"
            icon={<AirIcon />}
          />
        </Grid>
        <Grid item xs={12} sm={6}>
          <RelayCard
            relay={relays.battery}
            label="Battery Power"
            icon={<BatteryChargingFullIcon />}
          />
        </Grid>
      </Grid>
    </>
  );
}
