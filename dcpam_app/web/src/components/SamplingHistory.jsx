import React, { useMemo } from "react";

/**
 * 采样历史列表 —— 测量模式与分析模式共用同一套。
 *
 * 合并了两套能力：搜索过滤 + 刷新（原分析模式）与
 * 勾选/全选/导出 ZIP/批量删除/单删（原测量模式）。
 *
 * 全选、导出、批量删除都只作用于当前过滤后可见的记录（filteredRecords）。
 */
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
}) {
  const visibleIds = useMemo(() => records.map((r) => r.id), [records]);
  const selectedCount = exportSelection.size;
  const allSelected =
    visibleIds.length > 0 && visibleIds.every((id) => exportSelection.has(id));
  const filtered = totalRecords != null && records.length !== totalRecords;

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
              className="link-button"
              disabled={!visibleIds.length}
              onClick={() => setAllExportSelection(allSelected ? [] : visibleIds)}
              title={allSelected ? "取消全选" : "全选当前列表"}
            >
              {allSelected ? "清除" : "全选"}
            </button>
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

        <input
          className="sample-filter"
          type="search"
          placeholder="按 id 或名称过滤"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />

        {error && <div className="capture-status status-error">{error}</div>}

        <div className="sample-list">
          {records.length === 0 ? (
            <div className="sample-empty">
              {totalRecords ? "无匹配采样" : "尚无采样记录"}
            </div>
          ) : (
            records.map((record) => {
              const active = record.id === selectedId;
              const picked = exportSelection.has(record.id);
              return (
                <div
                  key={record.id}
                  className={`sample-item-row${active ? " active" : ""}${picked ? " picked" : ""}`}
                >
                  <label
                    className="sample-item-check"
                    title="勾选后可批量导出或删除"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={picked}
                      onChange={() => toggleExportSelection(record.id)}
                    />
                  </label>
                  <button
                    type="button"
                    className="sample-item"
                    onClick={() => setSelectedId(record.id)}
                  >
                    <span>{record.id}</span>
                    <span className="sample-item-meta">n={record.valid_n ?? record.n}</span>
                  </button>
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
                </div>
              );
            })
          )}
        </div>

        {listStatus && listStatus.text && (
          <div className={`capture-status status-${listStatus.kind}`}>{listStatus.text}</div>
        )}
      </section>
    </div>
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
