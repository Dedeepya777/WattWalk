/** Human-in-the-loop question dialog with a 30 s countdown (plan 11.3, 7.10). */
import { useEffect, useState } from "react";
import { ApiFailure, postAnswer } from "../api";
import { useAppDispatch, useAppState } from "../state";

export function QuestionDialog() {
  const state = useAppState();
  const dispatch = useAppDispatch();
  const question = state.openQuestion;
  const [remaining, setRemaining] = useState(30);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setRemaining(30);
    setError(null);
    if (!question) return;
    const interval = window.setInterval(() => {
      setRemaining((value) => (value <= 1 ? 0 : value - 1));
    }, 1000);
    return () => window.clearInterval(interval);
  }, [question?.question_id]);

  if (!question) return null;

  const close = () => dispatch({ type: "question", question: null });

  const answer = async (choice: string) => {
    setBusy(true);
    setError(null);
    try {
      await postAnswer(state.selectedSid, {
        question_id: question.question_id,
        answer: choice,
      });
      close();
    } catch (failure) {
      setError(
        failure instanceof ApiFailure
          ? failure.status === 409
            ? "Answer not accepted (question expired)."
            : failure.message
          : "Answer not accepted.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onClick={close}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="question-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <h2 id="question-title">The agent needs one answer</h2>
          <span className={`countdown ${remaining <= 5 ? "urgent" : ""}`}>
            {remaining}s
          </span>
        </div>
        <p className="question-text">{question.text}</p>
        {question.attr ? (
          <p className="muted small">
            Attribute: {question.attr}
            {question.asset_id ? ` · asset ${question.asset_id}` : ""}
          </p>
        ) : null}
        <div className="choice-row">
          {question.choices.map((choice) => (
            <button
              key={choice}
              className="button"
              disabled={remaining === 0 || busy}
              onClick={() => void answer(choice)}
            >
              {choice}
            </button>
          ))}
        </div>
        {remaining === 0 ? (
          <p className="inline-error">
            Question expired. The attribute stays unknown; you can correct it later in the
            evidence card.
          </p>
        ) : null}
        {error ? <p className="inline-error">{error}</p> : null}
        <div className="modal-actions">
          <button className="button" onClick={close} disabled={busy}>
            Skip
          </button>
        </div>
      </div>
    </div>
  );
}
