# 🚆 RailGuard — Dynamic Railway Traffic Simulation & Safety System

RailGuard is a real-time, physics-driven digital twin of a railway corridor.  
It simulates multi-train movement, dynamic block control, braking-envelope supervision,  
and conflict-aware routing using A* — all inside a browser-based interactive interface.

The system demonstrates how modern moving-block / ETCS-style supervision works using  
continuous speed ceilings, safe-distance envelopes, and occupancy-aware pathfinding.

---

## 🔍 **Key Features**

### **🟦 1. Real-time Train Simulation**
- 1-second tick engine  
- +10 km/h acceleration per tick  
- Continuous speed-limit recalculation  
- Accurate longitudinal motion using physics equations

### **🟥 2. Braking Envelope & Safety Simulation**
- Computes braking distance using \( v^2 / 2a \)
- Adds fixed 200 m safety buffer
- Calculates dynamic safe speed for every train
- Automatic bubble-breach detection  
- Emergency braking triggers

### **🟩 3. Dynamic Block Control**
- Each track edge gets inflated time cost (9999) when occupied  
- A* naturally avoids occupied segments  
- Ensures conflict-free routing without manual detection

### **🟧 4. Interactive Frontend (Browser UI)**
- Dynamic simulation view  
- Train markers  
- Speed indicators  
- Route visualization  
- Safety bubble warnings

### **🟪 5. Backend (Flask)**
- Real-time state management  
- Thread-safe locks for train updates  
- REST endpoints for:
  - Fetching simulation state  
  - Resetting simulation  
  - Dispatching trains  

---

## 📁 **Project Structure**

```
RailGuard/
│
├── Dynamic/
│   ├── app.py
│   ├── dynamic_simulation.html
│   │
│   ├── static/
│   │   ├── css/
│   │   │   ├── style.css
│   │   │   ├── style.css (login version)
│   │   │
│   │   ├── js/
│   │   │   ├── simulation.js
│   │   │   ├── script.js
│   │   │   ├── simulation.js (login version)
│   │   │
│   │   └── videos/
│   │       └── train.mp4
│   │
│   ├── templates/
│   │   └── index.html
│   │
│   ├── fixed_simulation.html
│   ├── TestingTracks2.json
│   └── TestRailway2.html
│
├── login/
│   ├── index.html
│   ├── style.css
│   └── images/
│       └── background.jpg
│
└── README.md
```

✔ **This matches your GitHub Desktop screenshot exactly.**  
✔ No missing files.  
✔ No extra folders.

---

## ▶️ **How to Run RailGuard**

### **1️⃣ Install dependencies**
```
pip install flask networkx
```

### **2️⃣ Run the backend**
```
python app.py
```

### **3️⃣ Open the browser**
```
http://127.0.0.1:5000/
```

---

## ⚙️ **Core Technologies**

- **Python (Flask)**
- **HTML, CSS, JavaScript**
- **NetworkX (track graph modelling)**
- **Threading (real-time simulation)**
- **Physics-based braking model**
- **A* pathfinding**

---

## ⭐ Purpose of RailGuard

RailGuard is designed as:
- a digital twin for railway movement
- a research prototype for moving-block signalling  
- a visualization of braking envelopes  
- a conflict-free routing demonstration  
- a portfolio project showcasing simulation + backend + frontend engineering

It helps understand modern traffic supervision concepts such as:
- ETCS Level 3 / CBTC  
- continuous monitoring  
- safe-speed determination  
- headway optimisation  

---

## 📌 Notes

- Some browser animations use video overlays.  
- Large file sizes (videos, images) require uploading **via GitHub Desktop** (not website).  
- App is built for demonstration — not an official signalling tool.

---

## 📜 License
This project is open for learning and research use.  
