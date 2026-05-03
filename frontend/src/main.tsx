import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.tsx';
import './index.css';
import { syncManager } from './lib/syncManager';
import ErrorBoundary from './components/common/ErrorBoundary';
import { errorLogger } from './lib/errorLogger';

// Global error handlers
window.onerror = (message, source, lineno, colno, error) => {
  errorLogger.log({
    message: typeof message === 'string' ? message : 'Global window error',
    stack: error?.stack || `at ${source}:${lineno}:${colno}`,
    level: 'FATAL',
  });
};

window.onunhandledrejection = (event) => {
  errorLogger.log({
    message: `Unhandled Promise Rejection: ${event.reason}`,
    level: 'ERROR',
  });
};

// Initialize offline sync manager
syncManager.loadInitialData();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>,
);

