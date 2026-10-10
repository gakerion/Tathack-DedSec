import "./HowToUse.css";

function HowToUse() {
  return (
    <div className="how-to-use">
      <article className="how-to-use-card">
        <section className="how-to-use-section">
          <h1>What is HoneyGate?</h1>

          <p>
            <strong>HoneyGate™</strong> is a security layer designed with{" "}
            <strong>multi-agentic AI</strong> in mind, though it works on
            simple LLMs as well. It identifies all the actions an AI model
            performs and classifies them based on risk using a{" "}
            <strong>DedSec</strong> designed{" "}
            <strong>case-specific-custom</strong> algorithm called{" "}
            <strong>BeeGate™</strong>.
          </p>

          <p className="how-to-use-quote">
            <strong>
              “A git inspired multi-agentic security software.”
            </strong>
          </p>
        </section>

        <section className="how-to-use-section">
          <h2>How to use?</h2>

          <p>
            Simple as it is to use a modern chatbot website since{" "}
            <strong>HoneyGate™</strong> uses the same user interface.
            The <strong>BeeGate™</strong> algorithm assigns colors to
            checkpoint actions based on importance score.
          </p>

          <ul className="how-to-use-colors">
            <li>
              <span className="how-to-use-dash" aria-hidden="true">-</span>
              <span>
                <strong className="importance-red">Red</strong> color
                indicates high importance score.
              </span>
            </li>

            <li>
              <span className="how-to-use-dash" aria-hidden="true">-</span>
              <span>
                <strong className="importance-yellow">Yellow</strong> color
                indicates medium importance score.
              </span>
            </li>

            <li>
              <span className="how-to-use-dash" aria-hidden="true">-</span>
              <span>
                <strong className="importance-green">Green</strong> color
                indicates low importance score.
              </span>
            </li>
          </ul>
        </section>
      </article>
    </div>
  );
}

export default HowToUse;