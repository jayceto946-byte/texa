import { Component, type ReactNode } from 'react';

export default class StartupBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidMount() { if (!this.state.failed) window.texaStartup?.ready(); }
  componentDidCatch(error: Error) { window.texaStartup?.fail('react-render', error); }
  render() { return this.state.failed ? null : this.props.children; }
}
