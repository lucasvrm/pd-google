import { DocumentManager } from './components/DocumentManager';

function App() {
  // Hardcoded entity for demo purposes
  const entityType = 'client';
  const entityId = '123';

  return (
    <div className="App">
      <h1>PipeDesk Drive Integration</h1>
      <DocumentManager entityType={entityType} entityId={entityId} />
    </div>
  );
}

export default App;
