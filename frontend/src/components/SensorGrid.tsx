import { Grid, Typography } from "@mui/material";
import SensorCard from "./SensorCard";
import type { SensorData, Config } from "../types";

interface Props {
  sensors: SensorData[];
  config: Config;
}

export default function SensorGrid({ sensors, config }: Props) {
  return (
    <>
      <Typography variant="overline" color="text.secondary" sx={{ pl: 0.5 }}>
        Temperature Sensors
      </Typography>
      <Grid container spacing={1.5}>
        {sensors.map((s) => (
          <Grid item xs={6} sm={4} md={3} key={s.sensor_id}>
            <SensorCard sensor={s} config={config} />
          </Grid>
        ))}
      </Grid>
    </>
  );
}
