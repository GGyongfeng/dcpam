export function parseCsv(text) {
  if (!text) return [];
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];

    if (char === "\"" && quoted && next === "\"") {
      cell += "\"";
      index += 1;
    } else if (char === "\"") {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") index += 1;
      row.push(cell);
      if (row.some((value) => value !== "")) rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }

  row.push(cell);
  if (row.some((value) => value !== "")) rows.push(row);

  const header = rows.shift() || [];
  return rows.map((values) => Object.fromEntries(
    header.map((key, index) => [key, values[index] ?? ""]),
  ));
}

export function normalizeMeasurementRow(row) {
  if (row.name) return row;
  const version = (row.dataset_version || "v1").toUpperCase();
  const pair = String(row.pair_index || "0").padStart(2, "0");
  return { ...row, name: `L109D${row.position_cm}-${version}-${pair}` };
}

export function parseToml(text) {
  const data = {};
  let section = data;
  const lines = text.split(/\r?\n/);

  for (let index = 0; index < lines.length; index += 1) {
    let line = lines[index].replace(/#.*/, "").trim();
    if (!line) continue;

    const sectionMatch = line.match(/^\[(.+)]$/);
    if (sectionMatch) {
      section = ensurePath(data, sectionMatch[1].split("."));
      continue;
    }

    const assign = line.match(/^([A-Za-z0-9_]+)\s*=\s*(.+)$/);
    if (!assign) continue;

    let value = assign[2].trim();
    while (value.includes("[") && !balancedBrackets(value) && index + 1 < lines.length) {
      index += 1;
      value += lines[index].replace(/#.*/, "").trim();
    }
    section[assign[1]] = parseTomlValue(value);
  }

  return data;
}

function ensurePath(root, parts) {
  return parts.reduce((node, part) => {
    node[part] ||= {};
    return node[part];
  }, root);
}

function parseTomlValue(value) {
  if (value.startsWith("\"")) return value.slice(1, -1);
  if (value.startsWith("[")) return JSON.parse(value.replace(/,\s*]/g, "]"));
  return Number(value);
}

function balancedBrackets(value) {
  let depth = 0;
  for (const char of value) {
    if (char === "[") depth += 1;
    if (char === "]") depth -= 1;
  }
  return depth === 0;
}
