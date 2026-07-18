// --- PRODUCTION LOGIC (CONNECTS TO BACKEND) ---
let currentTopic = "";
let lastSpeaker = null;
let lastMessage = "";
let currentRound = 1;

// Full running transcript per side, fed to the ML Judge at the end of the
// debate so it scores the cumulative argument, not just the last line.
let transcriptA = [];
let transcriptB = [];

const topicInput = document.getElementById('topicInput');
const durationInput = document.getElementById('durationInput');
const startBtn = document.getElementById('startBtn');
const nextBtn = document.getElementById('nextTurnBtn');
const endDebateBtn = document.getElementById('endDebateBtn');
const feedA = document.getElementById('feedA');
const feedB = document.getElementById('feedB');

// Timer-driven auto-play state. The debate now runs on a configurable
// timer (default 5 min, minimum 2 min) instead of requiring a manual
// "Pass Turn" click for every single rebuttal.
let debateEndTime = null;
let autoPlayActive = false;

// New UI Selectors
const displayTopic = document.getElementById('displayTopic');
const networkStatus = document.getElementById('networkStatus');
const statusText = document.getElementById('statusText');
const dotA = document.getElementById('dotA');
const dotB = document.getElementById('dotB');
const globalDot = document.getElementById('globalDot');
const countdownClock = document.getElementById('countdownClock');

let countdownIntervalId = null;

const API_URL = "http://127.0.0.1:5000/api/debate";

function toggleTyping(agent, show) {
    const feed = agent === 'A' ? feedA : feedB;
    const existing = document.getElementById('typingIndicator');
    
    if (show) {
        if (!existing) {
            const typingHTML = `<div class="typing-wrapper" id="typingIndicator"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div>`;
            feed.insertAdjacentHTML('beforeend', typingHTML);
            feed.scrollTop = feed.scrollHeight;
        }
    } else {
        if (existing) existing.remove();
    }
}

function setActive(agent) {
    if (agent === 'A') {
        dotA.classList.add('active');
        dotB.classList.remove('active');
        statusText.textContent = `Awaiting API Response for Agent A... (Round ${currentRound})`;
    } else {
        dotB.classList.add('active');
        dotA.classList.remove('active');
        statusText.textContent = `Awaiting API Response for Agent B... (Round ${currentRound})`;
    }
}

function appendMessage(agent, text, round) {
    toggleTyping(agent, false); // Clear typing before posting
    
    const div = document.createElement('div');
    div.classList.add('msg', agent === 'A' ? 'msg-adv' : 'msg-chal');
    div.innerHTML = `
        <div class="round-tag">Round ${round} · ${agent === 'A' ? 'Advocate' : 'Challenger'}</div>
        <div class="msg-text">${text}</div>
    `;

    const feed = agent === 'A' ? feedA : feedB;
    feed.appendChild(div);
    feed.scrollTop = feed.scrollHeight;
}

function setProcessingState(isLoading) {
    startBtn.disabled = isLoading;
    nextBtn.disabled = isLoading;
    if (isLoading) {
        topicInput.disabled = true;
        networkStatus.textContent = "COMPUTING";
        networkStatus.style.color = "#eab308";
        networkStatus.style.borderColor = "rgba(234,179,8,0.3)";
    } else {
        networkStatus.textContent = "IDLE";
        networkStatus.style.color = "#8b5cf6";
        networkStatus.style.borderColor = "rgba(139,92,246,0.3)";
    }
}

startBtn.addEventListener('click', async () => {
    const topic = topicInput.value.trim();
    if (!topic) return alert("Please enter a custom topic first.");
    
    currentTopic = topic;
    displayTopic.textContent = `"${topic}"`;
    feedA.innerHTML = '';
    feedB.innerHTML = '';
    currentRound = 1;
    transcriptA = [];
    transcriptB = [];
    endDebateBtn.disabled = true;
    autoPlayActive = false;
    document.getElementById('judgeOverlay').style.display = 'none';

    // Start the timer THE MOMENT the button is clicked, visible on screen
    // immediately -- not after Agent A's first response comes back.
    const minutes = Math.max(2, parseInt(durationInput.value, 10) || 5);
    debateEndTime = Date.now() + minutes * 60 * 1000;
    durationInput.disabled = true;
    nextBtn.disabled = true;
    startCountdownDisplay();
    
    setProcessingState(true);
    globalDot.classList.add('live');
    
    setActive('A');
    toggleTyping('A', true);

    try {
        const response = await fetch(`${API_URL}/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic: currentTopic })
        });
        
        const data = await response.json();
        
        // Mocking the Backend logic returning 'Agent A' since the Python code is currently empty!
        lastSpeaker = "A"; 
        lastMessage = data.message || "I defend the topic! (Python Backend generated this)";
        transcriptA.push(lastMessage);
        
        appendMessage(lastSpeaker, lastMessage, currentRound);
        
        dotA.classList.remove('active');
        setProcessingState(false);
        endDebateBtn.disabled = true; // enabled automatically once the timer ends
        autoPlayActive = true;
        runAutoPlay();
        
    } catch (err) {
        console.error("Backend connection failed.", err);
        alert("Failed to connect to the AI Backend Python Server on port 5000!");
        setProcessingState(false);
        globalDot.classList.remove('live');
        toggleTyping('A', false);
    }
});

function startCountdownDisplay() {
    if (countdownIntervalId) clearInterval(countdownIntervalId);
    updateCountdownClock();
    countdownIntervalId = setInterval(updateCountdownClock, 1000);
}

function updateCountdownClock() {
    if (!debateEndTime) {
        countdownClock.textContent = "--:--";
        return;
    }
    const remainingMs = Math.max(0, debateEndTime - Date.now());
    const totalSec = Math.ceil(remainingMs / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    countdownClock.textContent = `${m}:${s.toString().padStart(2, '0')}`;

    if (remainingMs <= 0 && countdownIntervalId) {
        countdownClock.textContent = "0:00";
        clearInterval(countdownIntervalId);
        countdownIntervalId = null;
    }
}

function formatRemaining() {
    if (!debateEndTime) return "";
    const remainingMs = Math.max(0, debateEndTime - Date.now());
    const totalSec = Math.ceil(remainingMs / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m}:${s.toString().padStart(2, '0')} remaining`;
}

// Auto-play loop: keeps calling /next-turn back and forth until the
// configured debate duration elapses, then automatically triggers the
// ML Judge -- this is what makes the debate a genuine timed session
// instead of relying on manual "Pass Turn" clicks.
async function runAutoPlay() {
    if (!autoPlayActive) return;

    if (Date.now() >= debateEndTime) {
        autoPlayActive = false;
        statusText.textContent = "Timer elapsed. Compiling ML Judge verdict...";
        endDebateBtn.disabled = false;
        if (countdownIntervalId) { clearInterval(countdownIntervalId); countdownIntervalId = null; }
        countdownClock.textContent = "0:00";
        await runJudge();
        return;
    }

    const nextAgent = lastSpeaker === 'A' ? 'B' : 'A';
    setActive(nextAgent);
    statusText.textContent = `Awaiting API Response for Agent ${nextAgent}... (${formatRemaining()})`;
    toggleTyping(nextAgent, true);

    try {
        const response = await fetch(`${API_URL}/next-turn`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                topic: currentTopic,
                last_speaker: lastSpeaker,
                last_message: lastMessage
            })
        });

        const data = await response.json();

        lastSpeaker = data.agent || nextAgent;
        lastMessage = data.message || "I attack the topic! (Python Backend generated this)";
        (lastSpeaker === 'A' ? transcriptA : transcriptB).push(lastMessage);

        appendMessage(lastSpeaker, lastMessage, currentRound);

        if (lastSpeaker === 'B') currentRound++;

        dotA.classList.remove('active');
        dotB.classList.remove('active');
    } catch (err) {
        console.error(err);
        toggleTyping(nextAgent, false);
        statusText.textContent = "An agent failed to respond -- retrying next cycle...";
    }

    // Small pacing delay so turns are readable on screen rather than
    // slamming back-to-back the instant a fast model responds. Kept short
    // since the bulk of the wait is the model's own generation time anyway.
    setTimeout(runAutoPlay, 400);
}

nextBtn.addEventListener('click', async () => {
    setProcessingState(true);
    
    // Switch to whichever agent DID NOT speak last
    const nextAgent = lastSpeaker === 'A' ? 'B' : 'A';
    setActive(nextAgent);
    toggleTyping(nextAgent, true);

    try {
        const response = await fetch(`${API_URL}/next-turn`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                topic: currentTopic,
                last_speaker: lastSpeaker,
                last_message: lastMessage
            })
        });
        
        const data = await response.json();
        
        // Since backend is empty, fallback to nextAgent
        lastSpeaker = data.agent || nextAgent;
        lastMessage = data.message || "I attack the topic! (Python Backend generated this)";
        (lastSpeaker === 'A' ? transcriptA : transcriptB).push(lastMessage);
        
        appendMessage(lastSpeaker, lastMessage, currentRound);
        
        if (lastSpeaker === 'B') currentRound++; // Increment round after B goes
        
        setProcessingState(false);
        dotA.classList.remove('active');
        dotB.classList.remove('active');
        statusText.textContent = "API Idle. Waiting for User Execution...";
        
    } catch (err) {
        console.error(err);
        alert("Agent failed to respond.");
        setProcessingState(false);
        toggleTyping(nextAgent, false);
    }
});

// --- ML JUDGE (CONNECTS TO /api/machine-learning/*) ---
async function runJudge() {
    setProcessingState(true);
    endDebateBtn.disabled = true;
    nextBtn.disabled = true;
    statusText.textContent = "Debate concluded. ML Judge computing verdict...";

    const advocateText = transcriptA.join(" ");
    const challengerText = transcriptB.join(" ");

    try {
        // Train (or re-train) the regression judge on the historical dataset.
        const trainResp = await fetch(`${API_URL.replace('/debate', '/machine-learning')}/train`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        if (!trainResp.ok) throw new Error("Training endpoint failed.");

        // Score both sides' cumulative arguments.
        const evalResp = await fetch(`${API_URL.replace('/debate', '/machine-learning')}/evaluate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ advocate_text: advocateText, challenger_text: challengerText })
        });
        if (!evalResp.ok) throw new Error("Evaluation endpoint failed.");

        const evalData = await evalResp.json();
        const sA = Number(evalData.advocate_score).toFixed(1);
        const sB = Number(evalData.challenger_score).toFixed(1);
        const winner = evalData.winner;
        const winnerName = winner === 'A' ? 'Agent A (The Advocate)' : winner === 'B' ? 'Agent B (The Challenger)' : 'Neither side (Tie)';

        document.getElementById('scoreA').textContent = sA + ' / 10';
        document.getElementById('scoreB').textContent = sB + ' / 10';
        document.getElementById('barA').style.width = (parseFloat(sA) * 10) + '%';
        document.getElementById('barB').style.width = (parseFloat(sB) * 10) + '%';

        document.getElementById('verdictBox').innerHTML = `
            <strong>Winner: ${winnerName}</strong><br/><br/>
            The SciKit-Learn RandomForestRegressor analyzed the full transcript from both agents
            across ${currentRound} round(s) and computed a persuasiveness score for each side
            based on word count, vocabulary complexity, sentiment, and rhetorical emphasis.
        `;

        const metrics = evalData.metrics || {};
        document.getElementById('judgeMetrics').innerHTML = `
            <div class="metric"><div class="label">Model Used</div><div class="val">RandomForestRegressor</div></div>
            <div class="metric"><div class="label">Features Extracted</div><div class="val">Word Count · Complexity · Sentiment · Emphasis</div></div>
            <div class="metric"><div class="label">Mean Squared Error</div><div class="val">${metrics.mse ?? 'N/A'}</div></div>
            <div class="metric"><div class="label">R² Accuracy</div><div class="val">${metrics.r2_score ?? 'N/A'}</div></div>
        `;

        document.getElementById('judgeOverlay').style.display = 'flex';
        setProcessingState(false);
        statusText.textContent = "ML Verdict delivered.";
    } catch (err) {
        console.error("ML Judge failed.", err);
        alert("Failed to reach the ML Judge backend. Check the Flask server terminal.");
        setProcessingState(false);
        endDebateBtn.disabled = false;
        nextBtn.disabled = false;
    }
}

endDebateBtn.addEventListener('click', () => {
    autoPlayActive = false; // manual early-stop overrides the timer
    if (countdownIntervalId) { clearInterval(countdownIntervalId); countdownIntervalId = null; }
    runJudge();
});
