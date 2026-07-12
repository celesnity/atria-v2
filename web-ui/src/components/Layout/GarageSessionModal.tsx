import { useState } from 'react';
import { createPortal } from 'react-dom';
import { Wrench, X } from 'lucide-react';
import { useProjectsStore } from '../../stores/projects';

interface GarageSessionModalProps {
  isOpen: boolean;
  onClose: () => void;
}

/**
 * Garage repair session ("vibe repairing") — a chat anchored to a Repair
 * Order. RO/VIN/brand are mandatory: no RO, no repair session (the server
 * enforces the same rule with a 422). Creates the conversation through the
 * live New Chat path (ProjectService) with session metadata attached.
 */
export function GarageSessionModal({ isOpen, onClose }: GarageSessionModalProps) {
  const [roNumber, setRoNumber] = useState('');
  const [vin, setVin] = useState('');
  const [brand, setBrand] = useState('Rolls-Royce');
  const [technician, setTechnician] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const createWorkspaceConversation = useProjectsStore(s => s.createWorkspaceConversation);

  const incomplete = !roNumber.trim() || !vin.trim() || !brand.trim();

  const handleCreate = async () => {
    if (incomplete || isCreating) return;
    setIsCreating(true);
    setError(null);
    try {
      await createWorkspaceConversation(`${roNumber.trim()} · ${brand.trim()}`, {
        session_type: 'garage',
        ro_number: roNumber.trim(),
        vin: vin.trim(),
        brand: brand.trim(),
        ...(technician.trim() ? { technician: technician.trim() } : {}),
      });
      setRoNumber('');
      setVin('');
      setTechnician('');
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create garage session.');
    } finally {
      setIsCreating(false);
    }
  };

  if (!isOpen) return null;

  const modal = (
    <div
      className="fixed inset-0 z-[99999] flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="mx-4 w-full max-w-md rounded-xl bg-canvas shadow-modal"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-hairline-soft px-5 py-4">
          <h2 className="flex items-center gap-2 text-lg font-semibold text-ink">
            <Wrench className="h-4 w-4 text-amber-500" strokeWidth={1.5} />
            Garage repair session
          </h2>
          <button
            aria-label="Close dialog"
            onClick={onClose}
            className="rounded-md p-1 text-text-muted hover:bg-surface-soft hover:text-text-secondary"
          >
            <X className="h-[18px] w-[18px]" strokeWidth={1.5} />
          </button>
        </div>

        <div className="space-y-3 px-5 py-4">
          <p className="text-sm text-text-secondary">
            Anchored to a Repair Order — no RO, no repair session. The conversation becomes the
            work log when you close the job.
          </p>
          <input
            type="text"
            value={roNumber}
            onChange={e => setRoNumber(e.target.value)}
            placeholder="RO number * (e.g. RO-2026-0201)"
            className="w-full rounded-md border border-hairline-soft px-3 py-2 text-sm"
            autoFocus
          />
          <input
            type="text"
            value={vin}
            onChange={e => setVin(e.target.value)}
            placeholder="VIN *"
            className="w-full rounded-md border border-hairline-soft px-3 py-2 font-mono text-sm"
          />
          <div className="grid grid-cols-2 gap-2">
            <select
              value={brand}
              onChange={e => setBrand(e.target.value)}
              className="rounded-md border border-hairline-soft bg-canvas px-3 py-2 text-sm"
            >
              <option value="Rolls-Royce">Rolls-Royce</option>
              <option value="Lamborghini">Lamborghini</option>
              <option value="McLaren">McLaren</option>
            </select>
            <input
              type="text"
              value={technician}
              onChange={e => setTechnician(e.target.value)}
              placeholder="Technician (KTV)"
              className="rounded-md border border-hairline-soft px-3 py-2 text-sm"
            />
          </div>
          {incomplete && (
            <p className="text-xs text-text-muted">
              RO number, VIN and brand are required.
            </p>
          )}
          {error && <p className="text-sm text-semantic-danger">{error}</p>}
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-hairline-soft px-5 py-4">
          <button
            onClick={onClose}
            className="rounded-md border border-hairline-soft bg-canvas px-4 py-2 text-sm font-medium text-text-secondary hover:bg-surface-soft"
          >
            Cancel
          </button>
          <button
            onClick={handleCreate}
            disabled={incomplete || isCreating}
            className="rounded-md bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:cursor-not-allowed disabled:bg-gray-300"
          >
            {isCreating ? 'Creating…' : 'Start repair session'}
          </button>
        </div>
      </div>
    </div>
  );

  return createPortal(modal, document.body);
}
