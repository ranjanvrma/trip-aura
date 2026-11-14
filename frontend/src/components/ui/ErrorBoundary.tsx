import { Component, type ReactNode } from "react";

/** Catches a crash while rendering a page and offers a way out. Reset by giving it a new `key` (the route). */
export default class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error(error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="narrow">
        <section className="tile empty" role="alert">
          <h1 className="h2">Something went wrong on this page</h1>
          <p className="muted">Your saved trips are not affected. Reloading usually fixes it.</p>
          <div className="row gap-s wrap center">
            <button className="btn btn-primary" onClick={() => window.location.reload()}>Reload</button>
            <a className="btn btn-ghost" href="/">Go to the home page</a>
          </div>
        </section>
      </div>
    );
  }
}
