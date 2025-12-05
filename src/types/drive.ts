export interface DriveItem {
  id: string;
  name: string;
  mimeType: string;
  parents: string[];
  webViewLink?: string;
  createdTime?: string;
}

export interface DriveResponse {
  files: DriveItem[];
  permission: 'owner' | 'writer' | 'reader';
}

export interface CreateFolderRequest {
  name: string;
}
