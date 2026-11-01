import { Link } from "react-router-dom";
import { EmptyState } from "../components/ui";

export default function NotFound() {
  return (
    <div className="container page">
      <div className="card">
        <EmptyState title="Page not found" action={<Link to="/dashboard" className="btn btn-primary">Go to dashboard</Link>}>
          The page you are looking for does not exist.
        </EmptyState>
      </div>
    </div>
  );
}
