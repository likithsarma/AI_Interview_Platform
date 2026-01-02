import { useEffect, useRef, useState } from "react";
import { API_BASE } from "./config";

function App() {
  const [resumeText, setResumeText] = useState(null);
  const [resumeData, setResumeData] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [interviewStarted, setInterviewStarted] = useState(false);

  // ---------- Text to Speech ----------
  const speak = (text) => {
    if (!text) return;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "en-US";
    window.speechSynthesis.speak(utter);
  };

  // ---------- STEP 1: Upload Resume (FAST, no AI) ----------
  const uploadResume = async (file) => {
    try {
      setLoading(true);
      setStatus("Uploading resume…");

      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${API_BASE}/upload_resume`, {
        method: "POST",
        body: formData
      });

      const data = await res.json();

      if (!res.ok || data.error) {
        setStatus("Could not read resume. Try another PDF.");
        return;
      }

      setResumeText(data.resume_text);
      setStatus("Resume uploaded successfully ✔️");

    } catch (err) {
      console.error(err);
      setStatus("Backend is waking up. Please try again in a moment.");
    } finally {
      setLoading(false);
    }
  };

  // ---------- STEP 2: Parse Resume (AI) ----------
  const parseResume = async () => {
    try {
      setLoading(true);
      setStatus("Parsing resume with AI…");

      const res = await fetch(`${API_BASE}/parse_resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resume_text: resumeText })
      });

      const data = await res.json();
      setResumeData(data.resume);
      setStatus("Resume analyzed ✔️");

    } catch (err) {
      console.error(err);
      setStatus("Failed to analyze resume.");
    } finally {
      setLoading(false);
    }
  };

  // ---------- STEP 3: Generate Questions (AI) ----------
  const generateQuestions = async () => {
    try {
      setLoading(true);
      setStatus("Generating interview questions…");

      const res = await fetch(`${API_BASE}/generate_questions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resume: resumeData })
      });

      const data = await res.json();

      if (!data.questions || data.questions.length === 0) {
        setStatus("Could not generate questions.");
        return;
      }

      setQuestions(data.questions);
      setInterviewStarted(true);
      setCurrentIndex(0);
      setStatus("");

    } catch (err) {
      console.error(err);
      setStatus("Question generation failed.");
    } finally {
      setLoading(false);
    }
  };

  // ---------- Speech Recognition ----------
  const recognitionRef = useRef(null);

  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setStatus("Speech recognition not supported in this browser");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
    recognition.continuous = false;
    recognitionRef.current = recognition;
  }, []);

  const startRecording = () => {
    const recognition = recognitionRef.current;
    if (!recognition) return;

    setStatus("Listening…");
    recognition.start();

    recognition.onresult = async (event) => {
      const answer = event.results[0][0].transcript;
      setStatus("Analyzing answer…");

      try {
        const res = await fetch(`${API_BASE}/answer`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: questions[currentIndex].question,
            answer: answer
          })
        });

        const data = await res.json();
        setStatus(data.evaluation?.feedback || "Answer recorded");

        setTimeout(() => {
          if (currentIndex + 1 < questions.length) {
            setCurrentIndex((prev) => prev + 1);
          } else {
            setStatus("Interview completed 🎉");
          }
        }, 2500);

      } catch (err) {
        console.error(err);
        setStatus("Error evaluating answer.");
      }
    };
  };

  // ---------- Speak Question ----------
  useEffect(() => {
    if (interviewStarted && questions[currentIndex]) {
      speak(questions[currentIndex].question);
    }
  }, [currentIndex, interviewStarted, questions]);

  return (
    <div style={{ maxWidth: 600, margin: "40px auto", textAlign: "center" }}>
      <h2>🎤 AI Interview Platform</h2>

      {!resumeText && (
        <>
          <p>Upload your resume to start</p>
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => uploadResume(e.target.files[0])}
          />
        </>
      )}

      {resumeText && !resumeData && (
        <button onClick={parseResume}>
          ▶️ Analyze Resume
        </button>
      )}

      {resumeData && !interviewStarted && (
        <button onClick={generateQuestions}>
          ▶️ Start Interview
        </button>
      )}

      {interviewStarted && questions[currentIndex] && (
        <>
          <h3>
            Question {currentIndex + 1} of {questions.length}
          </h3>
          <p>{questions[currentIndex].question}</p>
          <button onClick={startRecording}>🎙️ Answer by Voice</button>
        </>
      )}

      {loading && <p>Processing…</p>}
      {status && <p><strong>{status}</strong></p>}
    </div>
  );
}

export default App;
