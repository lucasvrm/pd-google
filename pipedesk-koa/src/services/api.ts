import axios from 'axios';
import { DriveItem, CreateFolderRequest } from '../types/drive';

const API_BASE = 'http://localhost:8000';

export const driveApi = {
  // Get files for an entity (Client/Lead/etc)
  getFiles: async (entityType: string, entityId: string): Promise<DriveItem[]> => {
    const response = await axios.get(`${API_BASE}/drive/${entityType}/${entityId}`);
    return response.data;
  },

  // Create a subfolder
  createFolder: async (entityType: string, entityId: string, name: string): Promise<DriveItem> => {
    const payload: CreateFolderRequest = { name };
    const response = await axios.post(`${API_BASE}/drive/${entityType}/${entityId}/folder`, payload);
    return response.data;
  },

  // Upload a file
  uploadFile: async (entityType: string, entityId: string, file: File): Promise<DriveItem> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await axios.post(`${API_BASE}/drive/${entityType}/${entityId}/upload`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  }
};
