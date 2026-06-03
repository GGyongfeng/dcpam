import { useEffect, useState } from "react";

export function useStoredText(key) {
  const [value, setValue] = useState(() => localStorage.getItem(key) || "");

  useEffect(() => {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  }, [key, value]);

  return [value, setValue];
}
