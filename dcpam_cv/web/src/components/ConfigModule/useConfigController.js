import { useEffect, useMemo, useState } from "react";

import { useConfig } from "../../layout/useConfig.jsx";
import { deepClone, setIn } from "./utils.js";

/**
 * 集中管 config draft/保存/上传/下载/放弃。ConfigModule 内部各子组件共用同一个 controller。
 */
export function useConfigController() {
  const { data, path, loading, error, savedAt, save, uploadText, refresh } = useConfig();
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [uploadError, setUploadError] = useState("");

  useEffect(() => {
    if (data && !dirty) setDraft(deepClone(data));
  }, [data, dirty]);

  const patch = (p, value) => {
    setDraft((current) => setIn(current, p, value));
    setDirty(true);
  };

  const onSave = async () => {
    const ok = await save(draft);
    if (ok) setDirty(false);
  };

  const onUpload = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const text = await file.text();
    setUploadError("");
    const ok = await uploadText(text);
    if (!ok) setUploadError(error || "上传失败");
  };

  const onDownload = () => {
    window.location.href = "/api/config/download";
  };

  return useMemo(
    () => ({
      draft, dirty, loading, error, uploadError, savedAt, path,
      patch, onSave, onUpload, onDownload, refresh,
    }),
    [draft, dirty, loading, error, uploadError, savedAt, path],
  );
}
