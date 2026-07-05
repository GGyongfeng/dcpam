import { useStoredText } from "../storage.js";

const KEY = "dcpam.viewer.mainPanel";
const VALUES = ["3d", "process"];
const DEFAULT_VALUE = "3d";

export function useMainPanelLayout() {
  const [raw, setRaw] = useStoredText(KEY);
  const value = VALUES.includes(raw) ? raw : DEFAULT_VALUE;
  const setValue = (next) => setRaw(VALUES.includes(next) ? next : DEFAULT_VALUE);
  return [value, setValue];
}
