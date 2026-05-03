import React, { Component, ErrorInfo, ReactNode } from 'react';
import { errorLogger } from '../../lib/errorLogger';

interface Props {
  children?: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
}

class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false
  };

  public static getDerivedStateFromError(_: Error): State {
    // Update state so the next render will show the fallback UI.
    return { hasError: true };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    errorLogger.log({
      message: `React ErrorBoundary caught: ${error.message}`,
      stack: errorInfo.componentStack || error.stack,
      level: 'FATAL',
    });
  }

  public render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="flex flex-col items-center justify-center min-h-screen bg-slate-900 text-white p-6 text-center">
          <div className="bg-red-500/10 border border-red-500/20 p-8 rounded-2xl max-w-md backdrop-blur-xl shadow-2xl">
            <h1 className="text-3xl font-bold mb-4 bg-gradient-to-r from-red-400 to-rose-400 bg-clip-text text-transparent">
              Something went wrong
            </h1>
            <p className="text-slate-400 mb-6">
              An unexpected error occurred in the application. Our team has been notified.
            </p>
            <button
              onClick={() => window.location.reload()}
              className="px-6 py-2 bg-gradient-to-r from-indigo-500 to-purple-600 rounded-lg font-medium hover:scale-105 transition-transform shadow-lg shadow-indigo-500/20"
            >
              Reload Page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
