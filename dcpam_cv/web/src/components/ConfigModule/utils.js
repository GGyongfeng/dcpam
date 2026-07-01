export function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

export function setIn(obj, path, value) {
  const next = Array.isArray(obj) ? [...obj] : { ...obj };
  let cursor = next;
  for (let i = 0; i < path.length - 1; i += 1) {
    const key = path[i];
    const existing = cursor[key];
    cursor[key] = existing == null
      ? (typeof path[i + 1] === "number" ? [] : {})
      : (Array.isArray(existing) ? [...existing] : { ...existing });
    cursor = cursor[key];
  }
  cursor[path[path.length - 1]] = value;
  return next;
}

export function coerce(text, type) {
  if (text === "") return type === "text" ? "" : null;
  if (type === "text") return text;
  const num = Number(text);
  if (!Number.isFinite(num)) return null;
  return type === "int" ? Math.trunc(num) : num;
}
