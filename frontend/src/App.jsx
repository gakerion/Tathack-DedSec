import { useState } from "react";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import "./App.css";

import Layout from "./components/Layout";
import AboutUs from "./components/layouts/AboutUs";
import Chat from "./components/layouts/Chat";
import HowToUse from "./components/layouts/HowToUse";
import GeminiMistakes from "./assets/gemini-notice.png";

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      {
        index: true,
        element: <Chat />,
      },
      {
        path: "how-to-use",
        element: <HowToUse />,
      },
      {
        path: "about",
        element: <AboutUs />,
      },
    ],
  },
]);

const popupSteps = [
  {
    title: "HoneyGate",
    content: (
      <>
        <p>
          <strong>AI, AI, AI.</strong>
        </p>

        <p>
          Before you run behind the hype, have you ever thought of reading
          the message below any AI-generated content? Here's one of them.
          Take a look.
        </p>
      </>
    ),
    image: GeminiMistakes,
  },
  {
    title: "See the pattern?",
    content: (
      <>
        <p>
          AI <em>can</em> make mistakes. That's right. You might want to
          hold your security head from fainting, <em>just in case</em>.
        </p>

        <p>
          AI workflows need ways to <strong>track</strong>,{" "}
          <strong>log</strong> and <strong>override</strong> actions
          when something goes wrong.
        </p>

        <p>
          Here's where <strong>HoneyGate</strong> comes in.
        </p>

        <p>
          It is a <em>“Git-inspired multi-agentic security software.”</em>
        </p>
      </>
    ),
    image: null,
  },
  {
    title: "Multi-agentic AI Catastrophe",
    content: (
      <>
        <p>
          As <strong>multi-agentic AI</strong> becomes more capable and
          takes on longer tasks, a question arises: what happens if AI
          deletes or edits something it isn't supposed to?
        </p>

        <p>
          HoneyGate is designed as a security layer that works alongside
          these models to <strong>track</strong>, <strong>block</strong>{" "}
          and, where recovery is supported, <strong>revert</strong>{" "}
          their actions.
        </p>

        <p>
          <strong>HoneyGate</strong> uses <strong>BeeGate</strong>, a custom
          algorithm built by <strong>DedSec</strong>.
        </p>

        <p className="popup-hashtag">
          #Proudly_built_by_humans_for_humans
        </p>
      </>
    ),
    image: null,
  },
];

function App() {
  const [showPopup, setShowPopup] = useState(true);
  const [currentStep, setCurrentStep] = useState(0);

  const step = popupSteps[currentStep];
  const isLastStep = currentStep === popupSteps.length - 1;

  function handleNext() {
    if (isLastStep) {
      setShowPopup(false);
    } else {
      setCurrentStep((previous) => previous + 1);
    }
  }

  function handleClose() {
    setShowPopup(false);
  }

  return (
    <>
      <RouterProvider router={router} />

      {showPopup && (
        <div className="popup-overlay">
          <div className="popup-card">
            <div className="popup-header">
              <h2>{step.title}</h2>

              <button
                type="button"
                className="popup-close-x"
                onClick={handleClose}
                aria-label="Close introduction"
              >
                ×
              </button>
            </div>

            <div className="popup-body">
              <div className="popup-text">{step.content}</div>

              {step.image && (
                <div className="popup-image-wrapper">
                  <img
                    src={step.image}
                    alt="Gemini notice about possible AI mistakes"
                    className="popup-image"
                  />
                </div>
              )}
            </div>

            <div className="popup-footer">
              <div className="popup-pagination">
                {popupSteps.map((item, index) => (
                  <button
                    key={item.title}
                    type="button"
                    className={`pagination-square ${
                      index === currentStep ? "active" : ""
                    }`}
                    onClick={() => setCurrentStep(index)}
                    aria-label={`Show slide ${index + 1}`}
                    aria-current={
                      index === currentStep ? "step" : undefined
                    }
                  />
                ))}
              </div>

              <button
                type="button"
                className="popup-next-btn"
                onClick={handleNext}
              >
                {isLastStep ? "FINISH" : "NEXT"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default App;