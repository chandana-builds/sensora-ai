import { Link } from "react-router-dom";
import {
  Camera,
  Mic,
  CheckCircle2,
  ShieldAlert,
  FileText,
  SlidersHorizontal,
  ArrowRight,
  Eye,
  Check,
  Lock,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";

const STEPS = [
  {
    num: "1",
    title: "Explain naturally",
    text: "Describe the device malfunction in plain English. No cryptic error codes or model lookups needed.",
  },
  {
    num: "2",
    title: "Show the hardware",
    text: "Point your camera at indicators, serial stickers, or ports so Sensora grounds its reasoning in what is actually there.",
  },
  {
    num: "3",
    title: "One instruction at a time",
    text: "Follow a single atomic action tailored to your expertise level. Never get lost in an overwhelming checklist.",
  },
  {
    num: "4",
    title: "Verify before advancing",
    text: "Confirm your progress via user input and visual inspection before moving to the next diagnostic step.",
  },
];

const CAPABILITIES = [
  {
    icon: Mic,
    title: "Hands-Free Voice Interaction",
    text: "Push-to-talk speech transcription lets you keep both hands on tools and cables while communicating.",
  },
  {
    icon: Eye,
    title: "Camera-Assisted Context",
    text: "Direct frame inspection turns vague user symptoms into accurate diagnoses of light patterns, cabling, and switches.",
  },
  {
    icon: CheckCircle2,
    title: "Dual Verification Engine",
    text: "Guarantees safety by pairing user completion reports with independent visual camera verification.",
  },
  {
    icon: SlidersHorizontal,
    title: "Adaptive Guidance Level",
    text: "Choose beginner mode for step-by-step plain descriptions or experienced mode for terse, technical instructions.",
  },
  {
    icon: ShieldAlert,
    title: "Non-Negotiable Safety Escalation",
    text: "Immediate stoppage for hazards like smoke, sparking, gas, high voltage, or battery swelling.",
  },
  {
    icon: FileText,
    title: "Technician Handoff Reports",
    text: "Export structured diagnostic logs, completed steps, and observation timelines for professional handoffs.",
  },
];

export default function Landing() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="landing-page">
      {/* Hero Section */}
      <section className="hero">
        <div className="container hero-grid">
          <div className="hero-content">
            <p className="eyebrow">Multimodal Diagnostic Assistant</p>
            <h1>Understand and fix real-world problems through camera-guided assistance.</h1>
            <p className="lead">
              Sensora AI helps you troubleshoot devices, appliances, and electronics safely. Explain what happened, show the hardware, and receive verified, step-by-step guidance.
            </p>
            <div className="hero-actions">
              <Link to={isAuthenticated ? "/dashboard" : "/signup"} className="btn btn-primary btn-large">
                <span>{isAuthenticated ? "Go to Dashboard" : "Start Troubleshooting"}</span>
                <ArrowRight size={18} />
              </Link>
              <a href="#how" className="btn btn-secondary btn-large">
                How It Works
              </a>
            </div>
            <div className="status-note">
              <strong>Multimodal Workflow:</strong> Built on a 9-state diagnostic engine with dual user/visual verification and automated technician handoff generation.
            </div>
          </div>

          <div className="hero-graphic">
            <figure className="illustration" aria-label="Sensora AI live camera workflow preview">
              <div className="frame">
                <span className="corner tl" />
                <span className="corner tr" />
                <span className="corner bl" />
                <span className="corner br" />
                <div className="frame-overlay">
                  <Camera size={28} className="text-slate-400 mb-1" />
                  <span className="frame-label">Camera Inspection Feed</span>
                </div>
              </div>
              <ol className="mini-steps">
                <li className="done">
                  <Check size={14} className="text-emerald-400" />
                  <span>Inspect rear ethernet connector</span>
                </li>
                <li className="current">
                  <span className="dot" />
                  <span>Observe WAN indicator LED state</span>
                </li>
                <li>
                  <span className="small muted">Hold reset button for 10 seconds</span>
                </li>
              </ol>
              <figcaption>Live visual verification and state tracking.</figcaption>
            </figure>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="section">
        <div className="container">
          <p className="eyebrow">Proven Methodology</p>
          <h2>How Sensora Guides You to Resolution</h2>
          <div className="how-grid">
            {STEPS.map((step) => (
              <div key={step.num} className="card how-card">
                <span className="how-num">{step.num}</span>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Capabilities */}
      <section id="capabilities" className="section section-alt">
        <div className="container">
          <p className="eyebrow">Core Capabilities</p>
          <h2>Built for Real Diagnostic Demands</h2>
          <div className="cap-grid">
            {CAPABILITIES.map((cap) => {
              const IconComp = cap.icon;
              return (
                <div key={cap.title} className="cap">
                  <div className="cap-icon">
                    <IconComp size={20} />
                  </div>
                  <h3>{cap.title}</h3>
                  <p>{cap.text}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Privacy Callout */}
      <section className="section">
        <div className="container">
          <div className="card block-card">
            <div className="flex items-start gap-4">
              <div className="cap-icon flex-shrink-0">
                <Lock size={20} />
              </div>
              <div>
                <h3>Private and Consented by Design</h3>
                <p className="text-slate-600 mb-2">
                  Sensora AI does not stream video to third parties or store image frames without your explicit permission. All sessions are strictly isolated under your authenticated account or private guest token.
                </p>
                <div className="flex gap-2">
                  <span className="badge badge-verification">Row Level Security</span>
                  <span className="badge badge-verification">Zero Ad Tracking</span>
                  <span className="badge badge-verification">One-Click Full Data Export</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Bottom CTA */}
      <section className="section section-alt">
        <div className="container cta-inner">
          <div>
            <h2>Ready to diagnose a device?</h2>
            <p className="muted m-0">
              Start an interactive troubleshooting session in seconds.
            </p>
          </div>
          <div className="flex gap-3">
            <Link to={isAuthenticated ? "/live" : "/signup"} className="btn btn-primary btn-large">
              <span>{isAuthenticated ? "Launch Live Session" : "Create Free Account"}</span>
              <ArrowRight size={18} />
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
