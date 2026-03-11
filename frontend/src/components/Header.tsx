import {
  AppBar,
  Toolbar,
  Typography,
  Chip,
  Box,
  Tooltip,
} from "@mui/material";
import ThermostatIcon from "@mui/icons-material/Thermostat";
import WifiIcon from "@mui/icons-material/Wifi";
import WifiOffIcon from "@mui/icons-material/WifiOff";
import SyncIcon from "@mui/icons-material/Sync";
import type { SafetyStatus } from "../types";

type Status = "connecting" | "connected" | "disconnected";

interface Props {
  status: Status;
  lastSeen: number | null;
  safety?: SafetyStatus;
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString();
}

const statusConfig = {
  connected: { label: "Live", color: "success" as const, icon: <WifiIcon sx={{ fontSize: 14 }} /> },
  connecting: { label: "Connecting", color: "warning" as const, icon: <SyncIcon sx={{ fontSize: 14 }} /> },
  disconnected: { label: "Offline", color: "error" as const, icon: <WifiOffIcon sx={{ fontSize: 14 }} /> },
};

export default function Header({ status, lastSeen, safety }: Props) {
  const cfg = statusConfig[status];
  const batteryLocked = !!safety?.battery_lockout;
  const lockLabel =
    safety?.battery_lockout_reason === "over_temp"
      ? "Battery: Over Temp"
      : "Battery: No Reading";
  const lockReason =
    safety?.battery_lockout_reason === "over_temp"
      ? "Battery lockout: over temperature"
      : "Battery lockout: no valid temperature reading";

  return (
    <AppBar
      position="static"
      elevation={0}
      sx={{ bgcolor: "background.paper", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2 }}
    >
      <Toolbar sx={{ gap: 1.5 }}>
        <ThermostatIcon color="primary" />
        <Typography variant="h6" sx={{ flexGrow: 1, letterSpacing: 1 }}>
          Temp-Mon
        </Typography>

        {lastSeen && (
          <Typography variant="caption" color="text.secondary" sx={{ display: { xs: "none", sm: "block" } }}>
            Updated {formatTime(lastSeen)}
          </Typography>
        )}

        <Tooltip title={`Backend: ${status}`}>
          <Chip
            size="small"
            label={cfg.label}
            color={cfg.color}
            icon={cfg.icon}
          />
        </Tooltip>

        {batteryLocked && (
          <Tooltip title={lockReason}>
            <Chip
              size="small"
              label={lockLabel}
              color="error"
              variant="outlined"
            />
          </Tooltip>
        )}
      </Toolbar>
    </AppBar>
  );
}
