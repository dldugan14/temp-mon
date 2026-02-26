import { Box, Container, Stack, Typography, Alert } from "@mui/material";
import Header from "./components/Header";
import SensorGrid from "./components/SensorGrid";
import RelayPanel from "./components/RelayPanel";
import ConfigBounds from "./components/ConfigBounds";
import { useSystemState } from "./hooks/useSystemState";

export default function App() {
  const { state, status } = useSystemState();

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default", py: 2 }}>
      <Container maxWidth="lg">
        <Stack spacing={2}>
          <Header status={status} lastSeen={state?.timestamp ?? null} />

          {status === "disconnected" && (
            <Alert severity="error" variant="outlined">
              Lost connection to backend – retrying…
            </Alert>
          )}

          {status === "connecting" && !state && (
            <Alert severity="info" variant="outlined">
              Connecting to backend…
            </Alert>
          )}

          {state && (
            <>
              <SensorGrid
                sensors={state.sensors}
                config={state.config}
              />
              <RelayPanel relays={state.relays} />
              <ConfigBounds config={state.config} can={state.can} />
            </>
          )}

          {!state && status === "connected" && (
            <Typography color="text.secondary" align="center">
              Waiting for first sensor reading…
            </Typography>
          )}
        </Stack>
      </Container>
    </Box>
  );
}
