import { useEffect, useState, useRef, DragEvent } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Film, Upload } from "lucide-react";
import { useToast } from "../ui/Toast";
import { variants } from "../theme";

interface MediaItem {
  id: string;
  filename: string;
  size: number;
  url: string;
  content_type: string;
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

export default function MediaPanel({ apiBase }: { apiBase: string }) {
  const [media, setMedia] = useState<MediaItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { push } = useToast();

  const fetchMedia = () => {
    fetch(`${apiBase}/connector/media`)
      .then((r) => r.json())
      .then((d) => setMedia(d.media || []))
      .catch(() => {});
  };

  useEffect(() => { fetchMedia(); }, [apiBase]);

  const upload = async (file: File) => {
    setUploading(true);
    const reader = new FileReader();
    reader.onload = async () => {
      const b64 = (reader.result as string).split(",")[1];
      try {
        const res = await fetch(`${apiBase}/connector/media/upload`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filename: file.name, content_b64: b64, content_type: file.type }),
        });
        if (!res.ok) throw new Error("Upload failed");
        push(`Uploaded ${file.name}`, "success");
        fetchMedia();
      } catch (e) {
        push(`Upload failed: ${file.name}`, "error");
      } finally {
        setUploading(false);
      }
    };
    reader.readAsDataURL(file);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) upload(file);
  };

  return (
    <div style={{ padding: 20 }}>
      <h3 style={{ margin: "0 0 16px", color: "#e2e8f0", fontSize: 16, fontWeight: 600 }}>Media</h3>

      <motion.div
        animate={{ scale: dragging ? 1.02 : 1, borderColor: dragging ? "#2563EB" : "#22304D" }}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          border: "2px dashed #22304D",
          borderRadius: 12,
          padding: "28px 20px",
          textAlign: "center",
          cursor: "pointer",
          marginBottom: 20,
          background: dragging ? "#2563EB08" : "transparent",
          transition: "background 0.2s",
        }}
      >
        <Upload size={24} style={{ color: "#2563EB", marginBottom: 8 }} />
        <div style={{ color: "#94a3b8", fontSize: 13 }}>
          {uploading ? "Uploading…" : "Drop a file or click to upload"}
        </div>
        <input ref={inputRef} type="file" style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); }} />
      </motion.div>

      {media.length === 0 ? (
        <div style={{ color: "#64748b", textAlign: "center", padding: "20px 0", fontSize: 13 }}>No media files yet</div>
      ) : (
        <motion.div
          variants={variants.listContainer}
          initial="hidden"
          animate="visible"
          style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(160px,1fr))", gap: 12 }}
        >
          <AnimatePresence>
            {media.map((m) => (
              <motion.div
                key={m.id}
                layout
                variants={variants.listItem}
                exit="exit"
                whileHover={{ y: -2 }}
                style={{
                  background: "#111A2E", border: "1px solid #22304D",
                  borderRadius: 10, padding: "12px 14px",
                }}
              >
                <Film size={20} style={{ color: "#2563EB", marginBottom: 8 }} />
                <a
                  href={m.url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: "#e2e8f0", fontSize: 12, display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textDecoration: "none" }}
                  title={m.filename}
                >
                  {m.filename}
                </a>
                <div style={{ color: "#64748b", fontSize: 11, marginTop: 4 }}>{formatSize(m.size)}</div>
              </motion.div>
            ))}
          </AnimatePresence>
        </motion.div>
      )}
    </div>
  );
}
