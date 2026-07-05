import React, { createContext, useCallback, useContext, useEffect, useState } from "react";

const ConfigContext = createContext(null);

/**
 * 顶层 Provider：维护 config.toml 的 data/text，提供 refresh/save/uploadText。
 * 两个 mode 与 ConfigPanel 共享同一份。
 */
export function ConfigProvider({ children }) {
  const [data, setData] = useState(null);
  const [text, setText] = useState("");
  const [path, setPath] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [savedAt, setSavedAt] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/config");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      setData(payload.data);
      setText(payload.text);
      setPath(payload.path || "");
      setError("");
    } catch (err) {
      setError(`读取 config.toml 失败：${err.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  const save = useCallback(async (nextData) => {
    setLoading(true);
    try {
      const response = await fetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data: nextData }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.detail || `HTTP ${response.status}`);
      }
      setData(payload.data);
      setText(payload.text);
      setSavedAt(Date.now());
      setError("");
      return true;
    } catch (err) {
      setError(`保存失败：${err.message}`);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  const uploadText = useCallback(async (newText) => {
    setLoading(true);
    try {
      const response = await fetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: newText }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.detail || `HTTP ${response.status}`);
      }
      setData(payload.data);
      setText(payload.text);
      setSavedAt(Date.now());
      setError("");
      return true;
    } catch (err) {
      setError(`上传失败：${err.message}`);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const value = { data, text, path, loading, error, savedAt, refresh, save, uploadText };
  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
}

export function useConfig() {
  const ctx = useContext(ConfigContext);
  if (!ctx) throw new Error("useConfig must be used within ConfigProvider");
  return ctx;
}
