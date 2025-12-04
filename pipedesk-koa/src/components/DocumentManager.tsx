import React, { useEffect, useState } from 'react';
import { driveApi } from '../services/api';
import { DriveItem } from '../types/drive';

interface Props {
  entityType: string;
  entityId: string;
}

export const DocumentManager: React.FC<Props> = ({ entityType, entityId }) => {
  const [items, setItems] = useState<DriveItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');

  const loadFiles = async () => {
    setLoading(true);
    try {
      const data = await driveApi.getFiles(entityType, entityId);
      setItems(data);
    } catch (err) {
      console.error(err);
      alert('Error loading files');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFiles();
  }, [entityType, entityId]);

  const handleCreateFolder = async () => {
    if (!newFolderName) return;
    try {
      await driveApi.createFolder(entityType, entityId, newFolderName);
      setNewFolderName('');
      loadFiles();
    } catch (err) {
      console.error(err);
      alert('Error creating folder');
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    try {
      await driveApi.uploadFile(entityType, entityId, file);
      loadFiles();
    } catch (err) {
      console.error(err);
      alert('Error uploading file');
    }
  };

  return (
    <div style={{ padding: '20px', fontFamily: 'sans-serif' }}>
      <h2>Documents for {entityType} #{entityId}</h2>

      <div style={{ marginBottom: '20px', display: 'flex', gap: '10px' }}>
        <input
          type="text"
          placeholder="New Folder Name"
          value={newFolderName}
          onChange={(e) => setNewFolderName(e.target.value)}
        />
        <button onClick={handleCreateFolder}>Create Folder</button>
      </div>

      <div style={{ marginBottom: '20px' }}>
        <input type="file" onChange={handleFileUpload} />
      </div>

      {loading ? <p>Loading...</p> : (
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {items.map(item => (
            <li key={item.id} style={{
              padding: '10px',
              borderBottom: '1px solid #eee',
              display: 'flex',
              alignItems: 'center',
              gap: '10px'
            }}>
              <span>{item.mimeType === 'application/vnd.google-apps.folder' ? '📁' : '📄'}</span>
              <a href={item.webViewLink} target="_blank" rel="noreferrer" style={{ flexGrow: 1 }}>
                {item.name}
              </a>
              <span style={{ fontSize: '0.8em', color: '#666' }}>
                {item.mimeType}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
