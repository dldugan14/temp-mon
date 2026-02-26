export interface SensorData {
  index: number;
  sensor_id: string;
  name: string;
  temperature: number | null;
  error: boolean;
}

export interface RelayData {
  name: string;
  pin: number;
  state: boolean;
  is_overridden: boolean;
}

export interface Config {
  fan_on_temp: number;
  fan_off_temp: number;
  bat_on_temp: number;
  bat_off_temp: number;
  poll_interval: number;
}

export interface CanStatus {
  enabled: boolean;
  interface: string;
  last_cmd_at: number | null;
  last_cmd_relay: string | null;
  last_cmd_action: string | null;
  error: string | null;
  frame_count: number;
}

export interface SystemState {
  sensors: SensorData[];
  relays: {
    fan: RelayData;
    battery: RelayData;
  };
  timestamp: number;
  config: Config;
  can?: CanStatus;
}
