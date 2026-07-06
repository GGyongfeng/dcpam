import React, { useMemo } from "react";

/**
 * 采样历史 —— 测量模式与分析模式共用同一套，以纯表格形式呈现。
 *
 * 表格列由 DEFAULT_HISTORY_COLUMNS 定义，调用方可通过 columns 传入自定义列：
 * 每列形如 { key, header, className?, render(record, ctx) }，render 返回单元格内容。
 * ctx 里带 formatResult(record)，用于把外部算好的计算结果映射到「计算结果」列。
 *
 * 勾选列（含表头全选）、单行删除只作用于当前过滤后可见的记录（filteredRecords），
 * 顶部按钮的导出 / 批量删除同理。
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
  listStatus,
  columns = DEFAULT_HISTORY_COLUMNS,
  resultsById,
}) {
  const visibleIds = useMemo(() => records.map((r) => r.id), [records]);
  const selectedCount = exportSelection.size;
  const allSelected =
    visibleIds.length > 0 && visibleIds.every((id) => exportSelection.has(id));
  const filtered = totalRecords != null && records.length !== totalRecords;

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

  const totalCols = columns.length + 2; // 勾选列 + 删除列

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
              onClick={onRefresh}
              disabled={loading}
              title="重新读取本地 data/measurements 目录"
            >
              {loading ? "刷新中..." : "刷新"}
            </button>
          </div>
        </div>

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
              {records.length === 0 ? (
                <tr>
                  <td className="sample-empty" colSpan={totalCols}>
                    {totalRecords ? "无匹配采样" : "尚无采样记录"}
                  </td>
                </tr>
              ) : (
                records.map((record) => {
                  const active = record.id === selectedId;
                  const picked = exportSelection.has(record.id);
                  return (
                    <tr
                      key={record.id}
                      className={`sample-row${active ? " active" : ""}${picked ? " picked" : ""}`}
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
                          title="勾选后可批量导出或删除"
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
