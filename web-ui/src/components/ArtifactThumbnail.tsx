import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FileText, Trash2 } from 'lucide-react';
import type { Artifact } from '../types';
import { formatFileSize, isImageFile } from '../utils/fileUtils';

interface ArtifactThumbnailProps {
  artifact: Artifact;
  onDelete?: (artifactId: number) => void;
  onPreview?: (artifact: Artifact) => void;
  className?: string;
}

export function ArtifactThumbnail({
  artifact,
  onDelete,
  onPreview,
  className = '',
}: ArtifactThumbnailProps) {
  const { t } = useTranslation('artifacts');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [imageError, setImageError] = useState(false);

  const isImage = isImageFile(artifact.title || artifact.payload_ref || '');
  const isConversation = !!artifact.conversation_id;
  // Brand accent spine: cobalt = conversation, violet = project.
  const scopeColor = isConversation
    ? 'bg-accent-cobalt/12 text-accent-cobalt'
    : 'bg-accent-violet/12 text-accent-violet';
  const scopeLabel = isConversation ? t('panel.scopeConversation') : t('panel.scopeProject');

  const handleDelete = () => {
    onDelete?.(artifact.id);
    setShowDeleteConfirm(false);
  };

  return (
    <div
      className={`artifact-thumbnail relative group border border-hairline-soft/60 rounded-md overflow-hidden bg-canvas transition-all duration-fast hover:shadow-hover hover:border-accent-cobalt/40 ${className}`}
      onMouseLeave={() => setShowDeleteConfirm(false)}
    >
      {/* Preview Area */}
      <div
        className="w-full aspect-square bg-surface-soft/50 overflow-hidden cursor-pointer"
        onClick={() => onPreview?.(artifact)}
      >
        {isImage && artifact.preview && !imageError ? (
          <img
            src={artifact.preview}
            alt={artifact.title || t('thumbnail.altDefault')}
            className="w-full h-full object-cover"
            onError={() => setImageError(true)}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-surface-soft/60 to-hairline-soft/40">
            <FileText className="w-8 h-8 text-text-muted" strokeWidth={1.5} />
          </div>
        )}
      </div>

      {/* Info Section */}
      <div className="p-2.5 border-t border-hairline-soft/60">
        <div className="min-w-0 mb-2">
          <h3 className="text-[13px] font-medium text-ink truncate">
            {artifact.title || t('panel.untitled')}
          </h3>
          <p className="text-[10px] font-mono text-text-muted mt-0.5">
            {artifact.size ? formatFileSize(artifact.size) : t('thumbnail.unknownSize')}
          </p>
        </div>

        {/* Badges */}
        <div className="flex items-center gap-1.5">
          <span className={`inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded-[3px] ${scopeColor}`}>
            {scopeLabel}
          </span>
          <span className="inline-flex items-center text-[10px] font-mono px-1.5 py-0.5 rounded-[3px] bg-surface-soft/60 text-text-secondary truncate">
            {artifact.type}
          </span>
        </div>
      </div>

      {/* Hover Delete Button */}
      <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-fast">
        {!showDeleteConfirm ? (
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="p-1.5 bg-canvas/90 backdrop-blur-sm border border-hairline-soft/60 text-ink/50 hover:text-semantic-danger hover:border-semantic-danger/40 rounded-md shadow-soft transition-colors duration-fast cursor-pointer"
            title={t('thumbnail.deleteArtifact')}
            aria-label={t('thumbnail.deleteArtifact')}
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        ) : (
          <div className="absolute top-0 right-0 bg-canvas border border-semantic-danger/50 rounded-md shadow-modal p-2 whitespace-nowrap">
            <p className="text-[11px] font-mono text-text-secondary mb-2">{t('thumbnail.confirmDelete')}</p>
            <div className="flex gap-1">
              <button
                onClick={handleDelete}
                className="px-2 py-1 text-[11px] font-mono bg-semantic-danger text-white rounded hover:opacity-90 cursor-pointer transition-opacity"
              >
                {t('thumbnail.confirmYes')}
              </button>
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="px-2 py-1 text-[11px] font-mono border border-hairline-soft text-text-secondary rounded hover:bg-surface-soft cursor-pointer transition-colors"
              >
                {t('thumbnail.confirmNo')}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Created Date Tooltip */}
      <div className="absolute bottom-2 left-2 opacity-0 group-hover:opacity-100 transition-opacity duration-fast pointer-events-none">
        <div className="text-[10px] font-mono text-text-secondary bg-canvas/90 backdrop-blur-sm border border-hairline-soft/50 px-1.5 py-0.5 rounded">
          {new Date(artifact.created_at).toLocaleDateString()}
        </div>
      </div>
    </div>
  );
}
