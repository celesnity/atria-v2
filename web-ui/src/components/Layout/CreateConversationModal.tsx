import { useTranslation } from 'react-i18next';
import { useProjectsStore } from '../../stores/projects';
import { NameInputModal } from './NameInputModal';

interface Props {
  isOpen: boolean;
  projectId: string;
  projectName: string;
  onClose: () => void;
}

export function CreateConversationModal({ isOpen, projectId, projectName, onClose }: Props) {
  const { t } = useTranslation('layout');
  const createConversation = useProjectsStore(state => state.createConversation);
  return (
    <NameInputModal
      isOpen={isOpen}
      onClose={onClose}
      title={t('createConversationModal.title')}
      subtitle={<>in <span className="text-text-200">{projectName}</span></>}
      inputLabel={t('createConversationModal.inputLabel')}
      placeholder={t('createConversationModal.placeholder')}
      submitLabel={t('createConversationModal.submitLabel')}
      emptyError={t('createConversationModal.emptyError')}
      onSubmit={(name) => createConversation(projectId, name)}
    />
  );
}
