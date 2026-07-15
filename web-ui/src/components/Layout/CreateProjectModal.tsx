import { useTranslation } from 'react-i18next';
import { useProjectsStore } from '../../stores/projects';
import { NameInputModal } from './NameInputModal';

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export function CreateProjectModal({ isOpen, onClose }: Props) {
  const { t } = useTranslation('layout');
  const createProject = useProjectsStore(state => state.createProject);
  return (
    <NameInputModal
      isOpen={isOpen}
      onClose={onClose}
      title={t('createProjectModal.title')}
      inputLabel={t('createProjectModal.inputLabel')}
      placeholder={t('createProjectModal.placeholder')}
      submitLabel={t('createProjectModal.submitLabel')}
      emptyError={t('createProjectModal.emptyError')}
      onSubmit={createProject}
    >
      {(name) => {
        const slug = name.trim().toLowerCase().replace(/\s+/g, '-') || '<name>';
        return (
          <p className="text-xs text-text-400">
            {t('createProjectModal.folderLabel')} <code className="font-mono text-text-300">~/.minder/workspaces/…/{slug}/</code>
          </p>
        );
      }}
    </NameInputModal>
  );
}
