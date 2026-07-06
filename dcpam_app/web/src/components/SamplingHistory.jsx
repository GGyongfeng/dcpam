import React, { useMemo, useState } from "react";

import { useStoredJSON } from "../storage.js";

const UNGROUPED = "__ungrouped__";
const UNGROUPED_LABEL = "未分组";
const COLLAPSED_KEY = "dcpam.history.collapsedGroups";
const ORDER_KEY = "dcpam.history.groupOrder";

// 拖拽 dataTransfer 的两种载荷，用于区分「拖记录归组」与「拖组头排序」两种意图。
const DND_RECORD = "application/x-dcpam-record";
const DND_GROUP = "application/x-dcpam-group";


/**
 * 采样历史 —— 测量模式与分析模式共用同一套，以纯表格 + 分组折叠形式呈现。
 *
 * 列由 DEFAULT_HISTORY_COLUMNS 定义；columns 可自定义。
 *
 * 分组：
 *   - 顶部「+ 新建分组」建一个（可空）组；组名与采样名 name 相互独立。
 *   - 勾选若干行后，按住拖动其中任意一行到目标组头即可整批归入该组
 *     （拖动的是已勾选项；若拖的那行未勾选，则只移动它自己）。
 *   - 组头可点击折叠，折叠状态记在 localStorage。
 * 组名落盘：成员写在各自 sample.json 的 group；空组名单存 groups.json，由 groups prop 带入。
 */
export const DEFAULT_HISTORY_COLUMNS = [
  {
    key: "name",
    header: "名称",
    className: "col-name",
    render: (record) => record.name || record.id,
  },
  {
    key: "frames",
    header: "有效/总张数",
    className: "col-frames",
    render: (record) => `${record.valid_n ?? record.n ?? 0} / ${record.n ?? 0}`,
  },
  {
    key: "result",
    header: "计算结果",
    className: "col-result",
    render: (record, ctx) => ctx.formatResult(record),
  },
  {
    key: "ts",
    header: "拍照时间",
    className: "col-ts",
    render: (record) => formatTs(record.ts),
  },
];

export function SamplingHistory({
  records,
  totalRecords,
  selectedId,
  setSelectedId,
  filter,
  setFilter,
  onRefresh,
  loading,
  error,
  exportSelection,
  toggleExportSelection,
  setAllExportSelection,
  onExportZip,
  exporting,
  onDeleteRecords,
  onAssignGroup,
  onCreateGroup,
  groups: knownGroups = [],
  listStatus,
  columns = DEFAULT_HISTORY_COLUMNS,
  resultsById,
}) {
  const visibleIds = useMemo(() => records.map((r) => r.id), [records]);
  const selectedCount = exportSelection.size;
  const allSelected =
    visibleIds.length > 0 && visibleIds.every((id) => exportSelection.has(id));
  const filtered = totalRecords != null && records.length !== totalRecords;

  const [collapsedList, setCollapsedList] = useStoredJSON(COLLAPSED_KEY, []);
  const collapsed = useMemo(() => new Set(collapsedList), [collapsedList]);
  const toggleCollapsed = (key) =>
    setCollapsedList((prev) => {
      const set = new Set(prev);
      if (set.has(key)) set.delete(key);
      else set.add(key);
      return [...set];
    });

  const [creating, setCreating] = useState(false);
  const [groupInput, setGroupInput] = useState("");
  const [dragOverKey, setDragOverKey] = useState("");

  // 组顺序：一组 group key 的数组，存 localStorage。未在其中的组按组名补到末尾。
  const [orderList, setOrderList] = useStoredJSON(ORDER_KEY, []);

  const ctx = useMemo(
    () => ({
      resultsById,
      formatResult: (record) => {
        const res = resultsById?.[record.id];
        if (!res || !Number.isFinite(res.distanceMean)) return "—";
        return `${res.distanceMean.toFixed(2)} mm`;
      },
    }),
    [resultsById],
  );

  // 分组渲染：已知组（groups prop + 记录里出现过的）∪ 未分组。
  // 顺序按 orderList；orderList 里没有的组按组名排序补到末尾（未分组默认也排最后）。
  const groups = useMemo(() => {
    const buckets = new Map();
    for (const name of knownGroups) {
      const g = (name || "").trim();
      if (g) buckets.set(g, []);
    }
    for (const r of records) {
      const key = (r.group || "").trim() || UNGROUPED;
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key).push(r);
    }
    buckets.set(UNGROUPED, buckets.get(UNGROUPED) || []); // 未分组恒渲染

    const allKeys = [...buckets.keys()];
    const rank = new Map(orderList.map((k, i) => [k, i]));
    allKeys.sort((a, b) => {
      const ra = rank.has(a) ? rank.get(a) : Infinity;
      const rb = rank.has(b) ? rank.get(b) : Infinity;
      if (ra !== rb) return ra - rb;
      // 都不在 orderList 里：未分组垫底，其余按组名
      if (a === UNGROUPED) return 1;
      if (b === UNGROUPED) return -1;
      return a.localeCompare(b);
    });

    return allKeys.map((key) => ({
      key,
      label: key === UNGROUPED ? UNGROUPED_LABEL : key,
      groupName: key === UNGROUPED ? "" : key,
      rows: buckets.get(key) || [],
    }));
  }, [records, knownGroups, orderList]);

  // 把 dragKey 移动到 targetKey 之前，落盘新顺序（基于当前渲染顺序补全所有键）。
  const reorderGroups = (dragKey, targetKey) => {
    if (dragKey === targetKey) return;
    const current = groups.map((g) => g.key);
    const from = current.indexOf(dragKey);
    const to = current.indexOf(targetKey);
    if (from === -1 || to === -1) return;
    const next = [...current];
    next.splice(from, 1);
    next.splice(next.indexOf(targetKey), 0, dragKey);
    setOrderList(next);
  };

  const totalCols = columns.length + 2; // 勾选列 + 删除列


  const submitCreate = () => {
    const name = groupInput.trim();
    if (name) onCreateGroup?.(name);
    setCreating(false);
    setGroupInput("");
  };

  // 拖动一行到某组：若该行在勾选集里，则移动全部勾选项；否则只移动它自己。
  const onDropToGroup = (groupName, draggedId) => {
    const ids = exportSelection.has(draggedId) ? [...exportSelection] : [draggedId];
    onAssignGroup?.(ids, groupName);
    setDragOverKey("");
  };

  // 组头 drop：区分两种载荷 —— 拖来的是记录（归组）还是另一个组头（排序）。
  const onGroupHeaderDrop = (event, group) => {
    event.preventDefault();
    const groupKey = event.dataTransfer.getData(DND_GROUP);
    if (groupKey) {
      reorderGroups(groupKey, group.key);
      setDragOverKey("");
      return;
    }
    const recordId = event.dataTransfer.getData(DND_RECORD);
    if (recordId) onDropToGroup(group.groupName, recordId);
  };

  return (
    <div className="left-stack">
      <section className="section sample-list-section">
        <div className="section-title-row">
          <h3>
            采样历史 ({records.length}
            {filtered ? `/${totalRecords}` : ""})
          </h3>
          <div className="sample-list-actions">
            <button
              type="button"
              className="export-zip-button"
              disabled={exporting || selectedCount === 0}
              onClick={onExportZip}
              title={selectedCount === 0 ? "先勾选要导出的采样" : `导出 ${selectedCount} 个采样为 zip`}
            >
              {exporting ? "打包中..." : `导出 ZIP (${selectedCount})`}
            </button>
            <button
              type="button"
              className="delete-batch-button"
              disabled={selectedCount === 0}
              onClick={() => onDeleteRecords([...exportSelection])}
              title={selectedCount === 0 ? "先勾选要删除的采样" : `删除选中的 ${selectedCount} 个采样`}
            >
              {`删除 (${selectedCount})`}
            </button>
            <button
              type="button"
              className="link-button"
              onClick={() => {
                setGroupInput("");
                setCreating((v) => !v);
              }}
              title="新建一个分组，然后把勾选的采样拖进去"
            >
              + 新建分组
            </button>
            <button
              type="button"
              className="link-button"
              onClick={onRefresh}
              disabled={loading}
              title="重新读取本地 measurements 目录"
            >
              {loading ? "刷新中..." : "刷新"}
            </button>
          </div>
        </div>

        {creating && (
          <div className="group-assign-bar">
            <input
              className="group-assign-input"
              type="text"
              placeholder="新分组名称"
              value={groupInput}
              autoFocus
              onChange={(event) => setGroupInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") submitCreate();
                else if (event.key === "Escape") {
                  setCreating(false);
                  setGroupInput("");
                }
              }}
            />
            <button type="button" className="group-assign-ok" onClick={submitCreate}>
              新建
            </button>
            <button
              type="button"
              className="group-assign-cancel"
              onClick={() => {
                setCreating(false);
                setGroupInput("");
              }}
            >
              取消
            </button>
          </div>
        )}

        {error && <div className="capture-status status-error">{error}</div>}

        <div className="sample-table-wrap">
          <table className="sample-table">
            <thead>
              <tr>
                <th className="col-check">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    disabled={!visibleIds.length}
                    onChange={() => setAllExportSelection(allSelected ? [] : visibleIds)}
                    title={allSelected ? "取消全选" : "全选当前列表"}
                  />
                </th>
                {columns.map((col) => (
                  <th key={col.key} className={col.className}>
                    {col.header}
                  </th>
                ))}
                <th className="col-del" aria-label="删除" />
              </tr>
            </thead>
            <tbody>
              {records.length === 0 && knownGroups.length === 0 ? (
                <tr>
                  <td className="sample-empty" colSpan={totalCols}>
                    {totalRecords ? "无匹配采样" : "尚无采样记录"}
                  </td>
                </tr>
              ) : (
                groups.map((group) => {
                  const groupIds = group.rows.map((r) => r.id);
                  const groupAllSelected =
                    groupIds.length > 0 && groupIds.every((id) => exportSelection.has(id));
                  const isCollapsed = collapsed.has(group.key);
                  const isDropTarget = dragOverKey === group.key;
                  return (
                    <React.Fragment key={group.key}>
                      <tr
                        className={`group-header${isCollapsed ? " collapsed" : ""}${isDropTarget ? " drop-target" : ""}`}
                        draggable
                        onClick={() => toggleCollapsed(group.key)}
                        onDragStart={(event) => {
                          event.dataTransfer.setData(DND_GROUP, group.key);
                          event.dataTransfer.effectAllowed = "move";
                        }}
                        onDragOver={(event) => {
                          event.preventDefault();
                          if (dragOverKey !== group.key) setDragOverKey(group.key);
                        }}
                        onDragLeave={() => setDragOverKey((k) => (k === group.key ? "" : k))}
                        onDrop={(event) => onGroupHeaderDrop(event, group)}
                      >
                        <td
                          className="col-check"
                          onClick={(event) => event.stopPropagation()}
                        >
                          <input
                            type="checkbox"
                            checked={groupAllSelected}
                            disabled={groupIds.length === 0}
                            onChange={() => {
                              const next = new Set(exportSelection);
                              if (groupAllSelected) groupIds.forEach((id) => next.delete(id));
                              else groupIds.forEach((id) => next.add(id));
                              setAllExportSelection([...next]);
                            }}
                            title={groupAllSelected ? "取消勾选本组" : "勾选本组"}
                          />
                        </td>
                        <td className="group-header-cell" colSpan={totalCols - 1}>
                          <span className="group-grip" aria-hidden>⋮⋮</span>
                          <span className="group-caret" aria-hidden>▸</span>
                          <span className="group-name">{group.label}</span>
                          <span className="group-count">({group.rows.length})</span>
                        </td>
                      </tr>
                      {!isCollapsed &&
                        group.rows.map((record) => {
                          const active = record.id === selectedId;
                          const picked = exportSelection.has(record.id);
                          return (
                            <tr
                              key={record.id}
                              className={`sample-row${active ? " active" : ""}${picked ? " picked" : ""}`}
                              draggable
                              onDragStart={(event) => {
                                event.dataTransfer.setData(DND_RECORD, record.id);
                                event.dataTransfer.effectAllowed = "move";
                              }}
                              onClick={() => setSelectedId(record.id)}
                            >
                              <td
                                className="col-check"
                                onClick={(event) => event.stopPropagation()}
                              >
                                <input
                                  type="checkbox"
                                  checked={picked}
                                  onChange={() => toggleExportSelection(record.id)}
                                  title="勾选后可批量导出、拖动分组或删除"
                                />
                              </td>
                              {columns.map((col) => (
                                <td key={col.key} className={col.className}>
                                  {col.render(record, ctx)}
                                </td>
                              ))}
                              <td className="col-del">
                                <button
                                  type="button"
                                  className="sample-item-delete"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    onDeleteRecords([record.id]);
                                  }}
                                  title={`删除 ${record.id}`}
                                  aria-label={`删除 ${record.id}`}
                                >
                                  <TrashIcon />
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                    </React.Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {listStatus && listStatus.text && (
          <div className={`capture-status status-${listStatus.kind}`}>{listStatus.text}</div>
        )}
      </section>
    </div>
  );
}

function formatTs(ts) {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  const pad = (n) => String(n).padStart(2, "0");
  return (
    `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  );
}

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}
