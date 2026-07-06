import { useEffect, useState } from "react";

export function useStoredText(key) {
  const [value, setValue] = useState(() => localStorage.getItem(key) || "");

  useEffect(() => {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  }, [key, value]);

  return [value, setValue];
}

/**
 * 持久化任意可 JSON 序列化的值（数组 / 对象等）到 localStorage。
 * 解析失败时回退到 fallback。用于「已折叠组名」这类结构化状态。
 */
export function useStoredJSON(key, fallback) {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw == null ? fallback : JSON.parse(raw);
    } catch (_) {
      return fallback;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (_) {
      // 存储不可用（隐私模式等）时静默忽略
    }
  }, [key, value]);

  return [value, setValue];
}
