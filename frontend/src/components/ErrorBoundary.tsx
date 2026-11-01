import { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RefreshCw, Home } from "lucide-react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Sensora React ErrorBoundary caught an error:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="container page narrow" style={{ minHeight: "60vh", display: "grid", placeItems: "center" }}>
          <div className="card p-6 text-center max-w-lg w-full">
            <div className="flex justify-center mb-3">
              <span className="p-3 bg-rose-100 text-rose-700 rounded-full">
                <AlertTriangle size={32} />
              </span>
            </div>
            <h2 className="text-xl font-bold mb-2">Something went wrong</h2>
            <p className="text-slate-600 text-sm mb-4">
              {this.state.error?.message || "An unexpected error occurred while rendering this view."}
            </p>
            <div className="flex gap-3 justify-center">
              <button
                className="btn btn-secondary flex items-center gap-2"
                onClick={() => window.location.href = "/dashboard"}
              >
                <Home size={16} />
                <span>Return to Dashboard</span>
              </button>
              <button
                className="btn btn-primary flex items-center gap-2"
                onClick={() => window.location.reload()}
              >
                <RefreshCw size={16} />
                <span>Reload Page</span>
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
