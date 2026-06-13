/* ============================================================
   PurohitSeva — frontend wired to real FastAPI + PostgreSQL
   ============================================================ */

/* ---------- API helper ---------- */
const API = "/api/v1";
let TOKEN = localStorage.getItem("token");

async function api(path, options = {}) {
  const res = await fetch(API + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(TOKEN ? { "Authorization": "Bearer " + TOKEN } : {}),
      ...options.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.status);
  }
  return res.json();
}

/* ---------- State ---------- */
let USER   = null;   // UserPublic from /auth/me
let PANDIT = null;   // PanditResponse from /pandits/me
let PUROHITS = [];   // PanditResponse[]
let SERVICES = [];   // ServiceCatalogueItem[]

let pendingBooking = false;
let customStaging  = [];     // new services staged before submit
let calCursor;               // current calendar month
let calendarEvents = [];     // cached upcoming bookings for calendar

/* ---------- Constants ---------- */
const AVA_COLORS = ["#a8442a","#7d5a1f","#5a2d6e","#1f6b5a","#8a1f3d","#3b5a8a","#6e4a1f","#2a6e8a","#7a2a2a"];
const SVC_ICONS  = {
  "Griha Pravesh":"🏠","Satyanarayana Vratam":"🙏","Ganapati Homam":"🐘",
  "Namakaranam":"👶","Annaprashana":"🍚","Vivaha (Wedding)":"💍",
  "Sudarshana Homam":"🔥","Rudrabhishekam":"🔱","Navagraha Shanti":"🪐",
  "Office Opening Pooja":"🏢","Upanayanam":"🧵","Vastu Shanti":"🧭",
};
const SLOTS = [
  {id:"morning", label:"Morning · 6:00–9:30"},
  {id:"midday",  label:"Midday · 10:30–13:30"},
  {id:"evening", label:"Evening · 16:30–19:30"},
];
const HORIZON = 14;
const TODAY   = new Date(); TODAY.setHours(0,0,0,0);

// Duration preset map for custom-service form
const DUR_MAP = {
  s1:{duration_slots:1}, s2:{duration_slots:2}, s3:{duration_slots:3},
  d2:{duration_days:2},  d3:{duration_days:3},  d4:{duration_days:4},
};

/* ---------- Utilities ---------- */
const fmt       = n => "₹" + n.toLocaleString("en-IN");
const dateKey   = d => d instanceof Date ? d.toISOString().slice(0,10) : d;
const addDays   = (d,n) => { const x=new Date(d); x.setDate(x.getDate()+n); return x; };
const initials  = name => name.replace(/^(Pt\.|Sri)\s*/,"").split(" ").map(w=>w[0]).slice(0,2).join("");
const durLabel  = pj => pj.duration_days
  ? `${pj.duration_days} days`
  : pj.duration_slots === 1 ? "≈2–3 hrs"
  : pj.duration_slots === 2 ? "≈ half day" : "Full day";

const fmtD = k => new Date(k+"T00:00:00").toLocaleDateString("en-IN",{weekday:"short",day:"numeric",month:"short"});

function showToast(html){
  const t = document.getElementById("toast");
  t.innerHTML = html; t.classList.add("show");
  clearTimeout(t._tm); t._tm = setTimeout(()=>t.classList.remove("show"), 3800);
}


/* ============================================================
   AUTH
   ============================================================ */

async function restoreSession(){
  if(!TOKEN) return;
  try {
    USER = await api("/auth/me");
    if(USER.is_pandit) PANDIT = await api("/pandits/me").catch(()=>null);
  } catch(e) {
    TOKEN = null; localStorage.removeItem("token");
    USER = null; PANDIT = null;
  }
}

function switchTab(tab){
  document.getElementById("pane-login").style.display  = tab==="login"  ? "block" : "none";
  document.getElementById("pane-signup").style.display = tab==="signup" ? "block" : "none";
  document.getElementById("tab-login").classList.toggle("active",  tab==="login");
  document.getElementById("tab-signup").classList.toggle("active", tab==="signup");
}

async function doLogin(){
  const email    = document.getElementById("li-mail").value.trim();
  const password = document.getElementById("li-pass").value;
  if(!email || !password){ showToast("⚠️ Email and password required."); return; }
  try {
    const data = await api("/auth/login",{method:"POST",body:JSON.stringify({email,password})});
    TOKEN = data.access_token;
    localStorage.setItem("token", TOKEN);
    USER   = data.user;
    PANDIT = null;
    if(USER.is_pandit) PANDIT = await api("/pandits/me").catch(()=>null);
    closeLogin(); renderAuthSlot();
    showToast(`🙏 Namaste, <b>${USER.name}</b>! You're logged in.`);
    if(pendingBooking){ pendingBooking=false; finalizeBooking(); }
  } catch(e){ showToast(`⚠️ Login failed: <b>${e.message}</b>`); }
}

async function doSignup(){
  const name     = document.getElementById("su-name").value.trim();
  const email    = document.getElementById("su-mail").value.trim();
  const password = document.getElementById("su-pass").value;
  const phone    = document.getElementById("su-phone").value.trim();
  if(!name || !email || !password){ showToast("⚠️ Name, email and password are required."); return; }
  if(password.length < 8){ showToast("⚠️ Password must be at least 8 characters."); return; }
  try {
    const body = {name, email, password};
    if(phone) body.phone = phone;
    const data = await api("/auth/signup",{method:"POST",body:JSON.stringify(body)});
    TOKEN = data.access_token;
    localStorage.setItem("token", TOKEN);
    USER   = data.user;
    PANDIT = null;
    closeLogin(); renderAuthSlot();
    showToast(`🙏 Welcome, <b>${USER.name}</b>! Your account is ready.`);
    if(pendingBooking){ pendingBooking=false; finalizeBooking(); }
  } catch(e){ showToast(`⚠️ Sign up failed: <b>${e.message}</b>`); }
}

function logout(){
  TOKEN=null; USER=null; PANDIT=null; calendarEvents=[];
  localStorage.removeItem("token");
  renderAuthSlot(); go('home');
  showToast("You've been logged out. <b>Phir milenge!</b>");
}

function openLogin(){ document.getElementById("login-veil").classList.add("open"); document.body.style.overflow="hidden"; }
function closeLogin(){ document.getElementById("login-veil").classList.remove("open"); document.body.style.overflow=""; pendingBooking=false; }
function requireLogin(){ if(USER) return true; openLogin(); return false; }
function enlistInfo(){ closeLogin(); closeProfileMenu(); if(!USER){ openLogin(); showToast("Login first, then enlist."); return; } go('enlist'); }


/* ============================================================
   DATA LOADING
   ============================================================ */

// Hyderabad centre coordinates — drives distance_km on each pandit card
const HYD_LAT = 17.385, HYD_LNG = 78.4867;

async function loadData(){
  [PUROHITS, SERVICES] = await Promise.all([
    api(`/pandits?lat=${HYD_LAT}&lng=${HYD_LNG}`),
    api("/services"),
  ]);
}

async function refreshData(){
  await loadData();
  document.getElementById("near-pooja").innerHTML =
    `<option value="">Any pooja</option>` + SERVICES.map(s=>`<option>${s.name}</option>`).join("");
  renderLanding();
}


/* ============================================================
   NAVIGATION
   ============================================================ */

function go(page, mode){
  closeProfileMenu();
  document.querySelectorAll(".page").forEach(p=>p.classList.remove("visible"));
  document.getElementById("page-"+page).classList.add("visible");
  document.querySelectorAll(".nav-link[data-page]").forEach(b=>b.classList.toggle("active",b.dataset.page===page));
  window.scrollTo({top:0});
  if(page==="near")     renderNear();
  if(page==="services") renderServices();
  if(page==="search"){  if(mode) setMode(mode); else renderSearch(); }
  if(page==="account")  renderAccount();
  if(page==="history")  renderHistory();
  if(page==="enlist"){  if(!USER){ go('home'); openLogin(); return; } renderEnlist(); }
  if(page==="pending")  renderPending();
  if(page==="upcoming") renderUpcoming();
  if(page==="calendar") { calendarEvents=[]; calCursor=new Date(TODAY.getFullYear(),TODAY.getMonth(),1); renderCalendar(); }
}


/* ============================================================
   AUTH SLOT (nav top-right)
   ============================================================ */

function renderAuthSlot(){
  const slot = document.getElementById("auth-slot");
  if(!USER){
    slot.innerHTML = `<button class="login-btn" onclick="openLogin()">Login / Sign up</button>`;
    return;
  }
  const panditItems = USER.is_pandit ? `
      <button onclick="openAddSvc()"><span class="mic">➕</span> Add Service</button>
      <button onclick="go('pending')"><span class="mic">📨</span> Pending Requests</button>
      <button onclick="go('upcoming')"><span class="mic">🗓</span> Upcoming Services</button>
      <button onclick="go('calendar')"><span class="mic">📅</span> Calendar</button>`
    : `<button onclick="go('enlist')"><span class="mic">🪔</span> Enlist as Purohit</button>`;
  slot.innerHTML = `
  <div class="profile-wrap" id="profile-wrap">
    <div class="profile-chip" onclick="toggleProfileMenu(event)">
      <div class="pava">${initials(USER.name)}</div>
      <span class="pname-sm">${USER.name}</span><span class="car">▾</span>
    </div>
    <div class="profile-menu">
      <div class="pm-head"><b>${USER.name}${USER.is_pandit?" · 🪔 Purohit":""}</b><span>${USER.email}</span></div>
      <button onclick="go('account')"><span class="mic">👤</span> Account Information</button>
      <button onclick="go('history')"><span class="mic">📜</span> History</button>
      ${panditItems}
      <button class="logout" onclick="logout()"><span class="mic">🚪</span> Logout</button>
    </div>
  </div>`;
}

function toggleProfileMenu(e){ e.stopPropagation(); document.getElementById("profile-wrap").classList.toggle("open"); }
function closeProfileMenu(){ const w=document.getElementById("profile-wrap"); if(w) w.classList.remove("open"); }
document.addEventListener("click", e=>{ const w=document.getElementById("profile-wrap"); if(w&&!w.contains(e.target)) w.classList.remove("open"); });


/* ============================================================
   LANDING
   ============================================================ */

function renderLanding(){
  document.getElementById("featured-grid").innerHTML =
    [...PUROHITS].sort((a,b)=>(b.rating||0)-(a.rating||0)).slice(0,3).map((p,i)=>purohitCard(p,i)).join("");
  document.getElementById("chip-cloud").innerHTML =
    SERVICES.map(s=>`<button class="svc-chip" onclick="go('services')">${s.icon||"🪔"} ${s.name}<span class="cnt">${s.pandit_count}</span></button>`).join("");
  animateCount("stat-purohits", PUROHITS.length);
  animateCount("stat-services", SERVICES.length);
}

function animateCount(id, target){
  const el=document.getElementById(id); let c=0;
  const t=setInterval(()=>{ c++; el.textContent=c+"+"; if(c>=target) clearInterval(t); },90);
}


/* ============================================================
   CARD RENDERER
   ============================================================ */

function purohitCard(pu, i, opts={}){
  const poojas = opts.poojas || pu.poojas;
  const list = poojas.map(pj=>
    `<li><span class="pname">${pj.name}</span><span class="pprice">${fmt(pj.price)}</span></li>`).join("");
  const langStr = Array.isArray(pu.languages) ? pu.languages.join(" · ") : "";
  const distChip = opts.showDist!==false && pu.distance_km!=null
    ? `<span class="dist-chip">${pu.distance_km} km</span>` : "";
  const startPrice = poojas.length ? Math.min(...poojas.map(x=>x.price)) : 0;
  return `<div class="pcard" style="animation:pageIn .5s ${i*0.06}s both">
    <div class="pcard-top">
      <div class="avatar" style="background:${AVA_COLORS[i%AVA_COLORS.length]}">${initials(pu.display_name)}</div>
      <div>
        <h3>${pu.display_name}</h3>
        <div class="pcard-meta">
          <span class="rating">★ ${pu.rating??'New'}</span><span>·</span><span>${pu.area}</span>
          ${distChip}
        </div>
        <div class="pcard-meta" style="margin-top:2px">${langStr}</div>
      </div>
    </div>
    <div class="pcard-body">
      <div class="pcard-label">${opts.label||"Poojas & Prices"}</div>
      <ul class="pooja-list">${list}</ul>
    </div>
    <div class="pcard-foot">
      <div class="from-price">Starting from<strong>${fmt(startPrice)}</strong></div>
      <button class="book-btn" onclick="openBooking('${pu.id}')">Book Now</button>
    </div>
  </div>`;
}


/* ============================================================
   NEAR ME
   ============================================================ */

function renderNear(){
  const radius = +document.getElementById("near-radius").value;
  const pooja  = document.getElementById("near-pooja").value;
  let list = radius < 100
    ? PUROHITS.filter(p=>p.distance_km!=null && p.distance_km<=radius)
    : [...PUROHITS];
  if(pooja) list = list.filter(p=>p.poojas.some(x=>x.name===pooja));
  list.sort((a,b)=>(a.distance_km??999)-(b.distance_km??999));
  document.getElementById("near-count").innerHTML = `<b>${list.length}</b> purohit${list.length!==1?"s":""} found`;
  document.getElementById("near-grid").innerHTML = list.length
    ? list.map((p,i)=>purohitCard(p,i)).join("")
    : `<div class="empty" style="grid-column:1/-1"><div class="big">🪷</div><p>No purohits in this radius — try widening it.</p></div>`;
}


/* ============================================================
   SERVICES
   ============================================================ */

function renderServices(){
  const sort = document.getElementById("svc-sort").value;
  let list = [...SERVICES];
  if(sort==="popular") list.sort((a,b)=>b.pandit_count-a.pandit_count);
  if(sort==="cheap")   list.sort((a,b)=>a.min_price-b.min_price);
  if(sort==="az")      list.sort((a,b)=>a.name.localeCompare(b.name));
  document.getElementById("svc-count").innerHTML =
    `<b>${list.length}</b> services compiled from ${PUROHITS.length} purohits`;
  document.getElementById("svc-grid").innerHTML = list.map((s,i)=>{
    const minis = s.pandits.slice(0,4).map((w,j)=>
      `<div class="mini" style="background:${AVA_COLORS[(i+j)%AVA_COLORS.length]}" title="${w.display_name}">${initials(w.display_name)}</div>`).join("");
    return `<div class="svc-card" style="animation:pageIn .5s ${i*0.05}s both" onclick="filterNearBy('${s.name.replace(/'/g,"\\'")}')">
      <div class="ico">${s.icon||"🪔"}</div>
      <h3>${s.name}</h3>
      <div class="range">${s.min_price===s.max_price ? fmt(s.min_price) : fmt(s.min_price)+" – "+fmt(s.max_price)}</div>
      <div class="avail"><b>${s.pandit_count} purohit${s.pandit_count!==1?"s":""}</b> offer this pooja</div>
      <div class="who">${minis}</div>
    </div>`;
  }).join("");
}

function filterNearBy(pooja){
  go('near');
  document.getElementById("near-pooja").value = pooja;
  document.getElementById("near-radius").value = "100";
  renderNear();
}


/* ============================================================
   SEARCH
   ============================================================ */

let searchMode = "price";
function setMode(m){
  searchMode = m;
  document.getElementById("mode-price").classList.toggle("on", m==="price");
  document.getElementById("mode-name").classList.toggle("on",  m==="name");
  document.getElementById("price-tools").style.display = m==="price" ? "flex" : "none";
  document.getElementById("name-tools").style.display  = m==="name"  ? "flex" : "none";
  renderSearch();
}

function renderSearch(){
  const grid  = document.getElementById("search-grid");
  const empty = document.getElementById("search-empty");
  let html="", count=0;

  if(searchMode==="price"){
    const budget = +document.getElementById("budget").value;
    const sort   = document.getElementById("price-sort").value;
    let list = PUROHITS
      .map(p=>({...p, within:p.poojas.filter(x=>x.price<=budget)}))
      .filter(p=>p.within.length);
    list.sort((a,b)=>sort==="low"
      ? Math.min(...a.within.map(x=>x.price)) - Math.min(...b.within.map(x=>x.price))
      : Math.min(...b.within.map(x=>x.price)) - Math.min(...a.within.map(x=>x.price)));
    count = list.length;
    html  = list.map((p,i)=>purohitCard(p,i,{poojas:p.within,label:"Within your budget"})).join("");
    document.getElementById("search-count").innerHTML = `<b>${count}</b> purohits with poojas in budget`;
  } else {
    const q    = document.getElementById("name-q").value.trim().toLowerCase();
    const list = q ? PUROHITS.filter(p=>p.display_name.toLowerCase().includes(q)) : PUROHITS;
    count = list.length;
    html  = list.map((p,i)=>purohitCard(p,i)).join("");
    document.getElementById("search-count2").innerHTML = `<b>${count}</b> match${count!==1?"es":""}`;
  }
  grid.innerHTML = html;
  empty.style.display = count ? "none" : "block";
}


/* ============================================================
   ACCOUNT
   ============================================================ */

function renderAccount(){
  if(!USER){ go('home'); openLogin(); return; }
  const since = new Date(USER.created_at).toLocaleDateString("en-IN",{month:"long",year:"numeric"});
  document.getElementById("acct-grid").innerHTML = `
    <div class="acct-side">
      <div class="bigava">${initials(USER.name)}</div>
      <h3>${USER.name}</h3>
      <div class="since">Member since ${since}</div>
    </div>
    <div class="acct-main">
      <h2>Account Information</h2>
      <div class="sub">These details are shared with your purohit when a booking is confirmed.</div>
      <div class="info-row"><div class="iic">🪪</div><div><div class="ik">Display name</div><div class="iv">${USER.name}</div></div></div>
      <div class="info-row"><div class="iic">✉️</div><div><div class="ik">Email</div><div class="iv">${USER.email}</div></div></div>
      <div class="info-row"><div class="iic">📱</div><div><div class="ik">Phone number</div><div class="iv">${USER.phone||"—"}</div></div></div>
      <div class="info-row"><div class="iic">📍</div><div><div class="ik">Default city</div><div class="iv">Hyderabad, Telangana</div></div></div>
    </div>`;
}


/* ============================================================
   PAYMENT HELPERS
   ============================================================ */

// Returns true when a booking's pooja starts within 48 h of right now.
function isUrgent(startDateStr){
  const startMs = new Date(startDateStr + "T00:00:00").getTime();
  const diffH   = (startMs - Date.now()) / 3_600_000;
  return diffH > 0 && diffH <= 48;
}

// Humanise a UTC deadline timestamp into "X h Y m left" / "Expired".
function deadlineLabel(paymentDueAt){
  if(!paymentDueAt) return "";
  // payment_due_at is an ISO 8601 string with timezone from the server
  const dueMs  = new Date(paymentDueAt).getTime();
  const diffMs = dueMs - Date.now();
  if(diffMs <= 0) return "Expired";
  const hrs  = Math.floor(diffMs / 3_600_000);
  const mins = Math.floor((diffMs % 3_600_000) / 60_000);
  return hrs > 0 ? `${hrs} h ${mins} m left` : `${mins} m left`;
}

// Open the Razorpay Checkout popup, then verify payment server-side.
async function startPayment(bookingId){
  let order;
  try {
    order = await api(`/bookings/${bookingId}/create-payment`, {method:"POST"});
  } catch(e){
    showToast(`⚠️ Could not initiate payment: <b>${e.message}</b>`);
    return;
  }

  const options = {
    key:         order.razorpay_key,
    amount:      order.amount,
    currency:    "INR",
    name:        "PurohitSeva",
    description: order.description,
    order_id:    order.razorpay_order_id,
    prefill:     {name: order.prefill_name, email: order.prefill_email, contact: order.prefill_phone},
    theme:       {color: "#7a1f1f"},
    handler: async function(response){
      try {
        await api(`/bookings/${bookingId}/verify-payment`, {
          method: "POST",
          body:   JSON.stringify({
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature:  response.razorpay_signature,
          }),
        });
        showToast("🎉 Payment confirmed! Your booking is now <b>confirmed</b>.");
        renderHistory();
      } catch(e){
        showToast(`⚠️ Verification failed: <b>${e.message}</b>`);
      }
    },
    modal: {
      ondismiss: ()=> showToast("Payment cancelled — your booking is still awaiting payment."),
    },
  };

  const rzp = new Razorpay(options);
  rzp.open();
}

/* ============================================================
   HISTORY
   ============================================================ */

const STATUS_LABEL = {
  pending:          "Pending",
  awaiting_payment: "Awaiting Payment",
  confirmed:        "Upcoming",
  completed:        "Completed",
  cancelled:        "Cancelled",
  declined:         "Declined",
  expired:          "Expired",
};
const STATUS_CLASS = {
  pending:          "pending",
  awaiting_payment: "awaiting_payment",
  confirmed:        "up",
  completed:        "done",
  cancelled:        "cancelled",
  declined:         "declined",
  expired:          "expired",
};

async function renderHistory(){
  if(!USER){ go('home'); openLogin(); return; }
  const el = document.getElementById("hist-list");
  el.innerHTML = `<div class="empty"><div class="big">⏳</div><p>Loading your bookings…</p></div>`;

  let bookings;
  try { bookings = await api("/me/bookings"); }
  catch(e){ el.innerHTML=`<div class="empty"><div class="big">⚠️</div><p>Could not load bookings.</p></div>`; return; }

  if(!bookings.length){
    el.innerHTML=`<div class="empty"><div class="big">🪷</div>
      <p>No bookings yet. Find a purohit and book your first pooja!</p>
      <button class="btn-saffron" style="margin-top:22px" onclick="go('near')">Purohits Near Me</button></div>`;
    return;
  }

  const fmtDate = x=>new Date(x+"T00:00:00").toLocaleDateString("en-IN",{weekday:"short",day:"numeric",month:"short",year:"numeric"});

  el.innerHTML = bookings.map(b=>{
    const slotLbls   = (b.slots||[]).map(id=>SLOTS.find(s=>s.id===id)?.label.split(" · ")[0]||id).join(" + ");
    const when       = b.duration_days
      ? `${fmtDate(b.start_date)} → ${fmtDate(b.end_date)} (${b.duration_days} days)`
      : `${fmtDate(b.start_date)} · ${(b.slots||[]).length===3?"Full day":slotLbls||"—"}`;
    const urgentCard = isUrgent(b.start_date) && b.status!=="completed" && b.status!=="cancelled";
    const urgentHtml = urgentCard ? `<span class="urgent-badge">URGENT</span>` : "";

    // Extra row for awaiting_payment: countdown + Pay button
    let payRow = "";
    if(b.status==="awaiting_payment"){
      const dl        = deadlineLabel(b.payment_due_at);
      const dlUrgent  = dl==="Expired" || dl.includes("m left") && !dl.includes("h");
      payRow = `
        <div style="display:flex;align-items:center;gap:10px;margin-top:10px;flex-wrap:wrap">
          <span class="deadline-chip ${dlUrgent?"urgent-deadline":""}">⏱ Pay by ${dl}</span>
          <button class="pay-btn" onclick="startPayment('${b.id}')">Pay ${fmt(b.price)} →</button>
        </div>`;
    }

    return `
    <div class="hist-card ${urgentCard?"urgent":""}">
      <div class="hic">${SVC_ICONS[b.pooja_name]||"🪔"}</div>
      <div class="hmain">
        <b>${b.pooja_name}</b>${urgentHtml}
        <div class="hwho">with ${b.pandit_name} · ${b.pandit_area}</div>
        <div class="hwhen">📅 ${when}</div>
        ${payRow}
      </div>
      <div class="hr">
        <div class="hp">${fmt(b.price)}</div>
        <span class="hstatus ${STATUS_CLASS[b.status]||""}">${STATUS_LABEL[b.status]||b.status}</span>
      </div>
    </div>`;
  }).join("");
}


/* ============================================================
   BOOKING FLOW
   ============================================================ */

let bk = {pu:null, poojaObj:null, day:null, slots:[], availMap:{}};

function openBooking(panditId){
  const pu = PUROHITS.find(p=>String(p.id)===String(panditId));
  if(!pu) return;
  bk = {pu, poojaObj:null, day:null, slots:[], availMap:{}};
  const i = PUROHITS.indexOf(pu);
  document.getElementById("modal-head").innerHTML = `
    <div class="avatar" style="background:${AVA_COLORS[i%AVA_COLORS.length]}">${initials(pu.display_name)}</div>
    <div><h3>${pu.display_name}</h3><div class="sub">★ ${pu.rating??'New'} · ${pu.area} · ${pu.languages.join(" · ")}</div></div>
    <button class="modal-x" onclick="closeBooking()">✕</button>`;
  renderModalServices();
  document.getElementById("m-schedule").innerHTML = "";
  document.getElementById("m-summary").style.display = "none";
  document.getElementById("veil").classList.add("open");
  document.body.style.overflow = "hidden";
}

function closeBooking(){
  document.getElementById("veil").classList.remove("open");
  document.body.style.overflow = "";
}

function renderModalServices(){
  document.getElementById("m-services").innerHTML = bk.pu.poojas.map(pj=>`
    <button class="svc-row ${bk.poojaObj && String(bk.poojaObj.service_id)===String(pj.service_id)?"sel":""}"
      onclick="pickPooja('${pj.service_id}')">
      <span class="si">${pj.icon||SVC_ICONS[pj.name]||"🪔"}</span>
      <span class="sn"><b>${pj.name}</b><span class="dur">⏱ ${durLabel(pj)}</span></span>
      <span class="sp">${fmt(pj.price)}</span>
    </button>`).join("");
}

async function pickPooja(serviceId){
  bk.poojaObj = bk.pu.poojas.find(p=>String(p.service_id)===String(serviceId));
  bk.day = null; bk.slots = []; bk.availMap = {};
  renderModalServices();
  document.getElementById("m-schedule").innerHTML = `<div class="muted-hint">Loading availability…</div>`;
  updateSummary();
  try {
    const avail = await api(`/pandits/${bk.pu.id}/availability?service_id=${serviceId}`);
    bk.availMap = {};
    avail.days.forEach(d=>{ bk.availMap[d.date] = d; });
  } catch(e){
    document.getElementById("m-schedule").innerHTML = `<div class="muted-hint">⚠️ Could not load availability.</div>`;
    return;
  }
  renderSchedule();
}

function renderSchedule(){
  const pj    = bk.poojaObj;
  const multi = !!pj.duration_days;
  let cells   = "";
  for(let i=0;i<HORIZON;i++){
    const day  = addDays(TODAY,i);
    const dk   = dateKey(day);
    const avail = bk.availMap[dk]||{free_slots:[],is_span_start:false};
    const need  = pj.duration_slots||1;
    const ok    = multi ? avail.is_span_start : avail.free_slots.length>=need;
    const isSel = bk.day && dk===dateKey(bk.day);
    const inSpan= multi && bk.day && day>bk.day && day<=addDays(bk.day,pj.duration_days-1);
    const fc    = avail.free_slots.length;
    const status= ok ? (multi?"start ok":(fc===3?"free":fc+" slot"+(fc>1?"s":""))) : "busy";
    cells += `<div class="day-cell ${ok?"":"off"} ${isSel?"sel":""} ${inSpan?"span":""}"
      ${ok?`onclick="pickDay(${i})"`:""}>
      <div class="dow">${day.toLocaleDateString("en-IN",{weekday:"short"})}</div>
      <div class="dnum">${day.getDate()}</div>
      <div class="dst">${status}</div>
    </div>`;
  }

  let slotHtml = "";
  if(!multi && bk.day){
    const dk   = dateKey(bk.day);
    const free = (bk.availMap[dk]||{free_slots:[]}).free_slots;
    const need = pj.duration_slots||1;
    slotHtml = `<div class="mstep-label">3 · Pick ${need>1?need+" consecutive slots":"a slot"}</div>
      <div class="slot-chips">`+
      SLOTS.map(s=>`<button class="slot-chip ${bk.slots.includes(s.id)?"sel":""}"
        ${free.includes(s.id)?`onclick="pickSlot('${s.id}')"`:"disabled"}>${s.label}</button>`).join("")+
      `</div>`;
  }

  const hint = multi
    ? `Needs <b>${pj.duration_days} consecutive free days</b> — valid start dates are enabled; the span is highlighted.`
    : pj.duration_slots===3 ? "Full-day ceremony — only completely free days are enabled."
    : `Needs ${pj.duration_slots} free slot${pj.duration_slots>1?"s":""} in a day.`;

  document.getElementById("m-schedule").innerHTML =
    `<div class="mstep-label">2 · Pick a ${multi?"start ":""}date</div>
     <div class="day-strip">${cells}</div>
     <div class="muted-hint">${hint}</div>${slotHtml}`;
}

function pickDay(offset){
  const pj   = bk.poojaObj;
  bk.day     = addDays(TODAY,offset);
  if(pj.duration_days){ bk.slots=[]; }
  else if(pj.duration_slots===3){ bk.slots=SLOTS.map(s=>s.id); }
  else {
    bk.slots=[];
    if(pj.duration_slots===2){
      const free=(bk.availMap[dateKey(bk.day)]||{free_slots:[]}).free_slots;
      for(let i=0;i<SLOTS.length-1;i++){
        const a=SLOTS[i].id, b=SLOTS[i+1].id;
        if(free.includes(a)&&free.includes(b)){ bk.slots=[a,b]; break; }
      }
    }
  }
  renderSchedule(); updateSummary();
}

function pickSlot(id){
  const need = bk.poojaObj.duration_slots||1;
  if(need===1){ bk.slots=[id]; }
  else {
    if(bk.slots.includes(id)) bk.slots=bk.slots.filter(s=>s!==id);
    else {
      bk.slots=[...bk.slots,id];
      const order=SLOTS.map(s=>s.id);
      bk.slots.sort((a,b)=>order.indexOf(a)-order.indexOf(b));
      const idxs=bk.slots.map(s=>order.indexOf(s));
      const consecutive=idxs.every((v,i)=>i===0||v===idxs[i-1]+1);
      if(bk.slots.length>need||!consecutive) bk.slots=[id];
    }
  }
  renderSchedule(); updateSummary();
}

function updateSummary(){
  const box=document.getElementById("m-summary");
  if(!bk.poojaObj){ box.style.display="none"; return; }
  const pj=bk.poojaObj;
  const fmtDate=x=>x.toLocaleDateString("en-IN",{weekday:"short",day:"numeric",month:"short"});
  let when="—", ready=false;
  if(pj.duration_days && bk.day){
    when=`${fmtDate(bk.day)} → ${fmtDate(addDays(bk.day,pj.duration_days-1))} (${pj.duration_days} days)`;
    ready=true;
  } else if(!pj.duration_days && bk.day && bk.slots.length===(pj.duration_slots||1)){
    const lbls=bk.slots.map(id=>SLOTS.find(s=>s.id===id).label.split(" · ")[0]).join(" + ");
    when=`${fmtDate(bk.day)} · ${pj.duration_slots===3?"Full day":lbls}`;
    ready=true;
  } else if(bk.day){
    when=`${fmtDate(bk.day)} · choose slot${(pj.duration_slots||1)>1?"s":""}`;
  }
  box.style.display="flex";
  box.innerHTML=`
    <div class="bs-txt"><b>${pj.name}</b> with ${bk.pu.display_name}<br>${when} · <b>${fmt(pj.price)}</b></div>
    <button class="confirm-btn" ${ready?"":"disabled"} onclick="confirmBooking()">Confirm Booking</button>`;
}

function confirmBooking(){
  if(!requireLogin()){ pendingBooking=true; return; }
  finalizeBooking();
}

async function finalizeBooking(){
  const pj = bk.poojaObj;
  try {
    await api("/bookings",{
      method:"POST",
      body:JSON.stringify({
        pandit_id:  bk.pu.id,
        service_id: pj.service_id,
        start_date: dateKey(bk.day),
        slots:      bk.slots,
      }),
    });
    closeBooking();
    showToast(`🪔 Booked! <b>${pj.name}</b> with ${bk.pu.display_name} — pending confirmation. See it in <b>History</b>.`);
    renderAuthSlot();
  } catch(e){
    showToast(`⚠️ Booking failed: <b>${e.message}</b>`);
  }
}

document.addEventListener("keydown", e=>{
  if(e.key==="Escape"){ closeBooking(); closeLogin(); closeProfileMenu(); closeAddSvc(); }
});


/* ============================================================
   PANDIT SIDE
   ============================================================ */

function guardPandit(){
  if(USER && USER.is_pandit) return true;
  go('home'); if(!USER) openLogin(); else showToast("Enlist as a purohit first to access this.");
  return false;
}

/* ---------- Enlist ---------- */

function svcPickRow(svc, prefix, i){
  const dl = svc.duration_days ? `${svc.duration_days} days`
    : svc.duration_slots===1 ? "≈2–3 hrs"
    : svc.duration_slots===2 ? "≈ half day" : "Full day";
  return `<div class="svc-pick" id="${prefix}-pick-${i}" data-service-id="${svc.id}">
    <div class="chk" onclick="togglePick('${prefix}',${i})"></div>
    <span class="si">${svc.icon||"🪔"}</span>
    <span class="sn"><b>${svc.name}</b><span class="dur">⏱ ${dl}</span></span>
    <input type="number" class="price-in" placeholder="₹ your price" disabled>
  </div>`;
}

function togglePick(prefix, i){
  const row = document.getElementById(`${prefix}-pick-${i}`);
  row.classList.toggle("on");
  const inp = row.querySelector(".price-in");
  inp.disabled = !row.classList.contains("on");
  row.querySelector(".chk").textContent = row.classList.contains("on")?"✓":"";
  if(!inp.disabled) inp.focus();
}

function collectPicked(prefix){
  const out=[];
  document.querySelectorAll(`[id^="${prefix}-pick-"].on`).forEach(row=>{
    const price=+row.querySelector(".price-in").value;
    if(price>0) out.push({service_id:row.dataset.serviceId, price});
  });
  return out;
}

function addCustomService(mode){
  const p = mode==="enlist"
    ? {n:"cu-name",d:"cu-dur",pr:"cu-price",out:"cu-added"}
    : {n:"as-name",d:"as-dur",pr:"as-price",out:null};
  const name  = document.getElementById(p.n).value.trim();
  const price = +document.getElementById(p.pr).value;
  const durKey= document.getElementById(p.d).value;
  if(!name||!price){ showToast("⚠️ Give the new pooja a <b>name and price</b>."); return; }
  if(SERVICES.some(s=>s.name===name)){ showToast(`<b>${name}</b> already exists — tick it in the list above.`); return; }
  const dur = DUR_MAP[durKey];
  customStaging.push({name, price, ...dur});
  document.getElementById(p.n).value=""; document.getElementById(p.pr).value="";
  const chipHtml = customStaging.map(c=>{
    const cl = c.duration_days?`${c.duration_days} days`:c.duration_slots===1?"≈2–3 hrs":c.duration_slots===2?"≈ half day":"Full day";
    return `<span class="svc-chip" style="cursor:default">🪔 ${c.name} · <b style="color:var(--saffron)">${fmt(c.price)}</b> · ${cl}</span>`;
  }).join(" ");
  if(p.out) document.getElementById(p.out).innerHTML=chipHtml;
  else showToast(`Added <b>${name}</b> — will save with your other ticks.`);
}

function renderEnlist(){
  document.getElementById("en-name").value = USER ? USER.name : "";
  customStaging=[];
  document.getElementById("cu-added").innerHTML="";
  document.getElementById("en-services").innerHTML = SERVICES.map((s,i)=>svcPickRow(s,"en",i)).join("");
}

async function submitEnlist(){
  const display_name = document.getElementById("en-name").value.trim();
  const area         = document.getElementById("en-area").value.trim()||"Hyderabad";
  const langsStr     = document.getElementById("en-langs").value.trim()||"Telugu";
  const languages    = langsStr.split(/[·,]+/).map(s=>s.trim()).filter(Boolean);
  const picked       = collectPicked("en");
  const all          = [...picked, ...customStaging];

  if(!display_name){ showToast("⚠️ Enter your <b>display name</b>."); return; }
  if(!all.length){   showToast("⚠️ Select at least <b>one service with a price</b>."); return; }
  const ticked = document.querySelectorAll('[id^="en-pick-"].on').length;
  if(picked.length<ticked){ showToast("⚠️ Some ticked services are <b>missing a price</b>."); return; }

  try {
    PANDIT = await api("/pandits",{method:"POST",body:JSON.stringify({display_name,area,languages})});
    USER.is_pandit = true;

    for(const svc of picked){
      await api("/pandits/me/services",{method:"POST",body:JSON.stringify({service_id:svc.service_id,price:svc.price})});
    }
    for(const svc of customStaging){
      await api("/pandits/me/services/new",{method:"POST",body:JSON.stringify(svc)});
    }

    PANDIT = await api("/pandits/me");
    await refreshData();
    customStaging=[];
    renderAuthSlot();
    go('pending');
    showToast(`🪔 Welcome aboard, <b>${display_name}</b>! You're live on the platform.`);
  } catch(e){ showToast(`⚠️ Enlist failed: <b>${e.message}</b>`); }
}

/* ---------- Pending Requests ---------- */

function reqWhen(r){
  if(r.duration_days)
    return `${fmtD(r.start_date)} → ${fmtD(r.end_date)} · ${r.duration_days} days`;
  const lbls=(r.slots||[]).map(id=>SLOTS.find(s=>s.id===id)?.label.split(" · ")[0]||id).join(" + ");
  return `${fmtD(r.start_date)} · ${(r.slots||[]).length===3?"Full day":lbls}`;
}

async function renderPending(){
  if(!guardPandit()) return;
  const el=document.getElementById("pending-list");
  el.innerHTML=`<div class="empty"><div class="big">⏳</div><p>Loading…</p></div>`;
  const reqs = await api("/me/requests").catch(e=>{ showToast("⚠️ "+e.message); return []; });
  if(!reqs.length){
    el.innerHTML=`<div class="empty"><div class="big">📭</div><p>No pending requests right now. New requests appear here when families book you.</p></div>`;
    return;
  }
  el.innerHTML=reqs.map(r=>{
    const urgent    = isUrgent(r.start_date);
    const urgentBdg = urgent ? `<span class="urgent-badge">URGENT</span>` : "";
    return `
    <div class="req-card ${urgent?"urgent":""}">
      <div style="font-size:26px;width:52px;height:52px;border-radius:14px;background:var(--cream-warm);display:grid;place-items:center;flex-shrink:0">${SVC_ICONS[r.pooja_name]||"🪔"}</div>
      <div style="flex:1">
        <div class="req-client">REQUEST FROM ${(r.user_name||"Anonymous").toUpperCase()}${urgentBdg}</div>
        <b style="font-family:'Marcellus',serif;font-size:17px;color:var(--maroon)">${r.pooja_name}</b>
        <div style="font-size:12.5px;font-weight:700;color:var(--ink-soft);margin-top:4px">📅 ${reqWhen(r)} · <span style="color:var(--maroon)">${fmt(r.price)}</span></div>
      </div>
      <div class="req-actions">
        <button class="acc-btn" onclick="acceptReq('${r.id}')">✓ Accept</button>
        <button class="dec-btn" onclick="declineReq('${r.id}')">Decline</button>
      </div>
    </div>`;
  }).join("");
}

async function acceptReq(id){
  try {
    await api(`/bookings/${id}/accept`,{method:"POST"});
    showToast("✓ Accepted — booking confirmed and added to your calendar.");
    calendarEvents=[];  // invalidate cache
    renderPending();
  } catch(e){ showToast(`⚠️ ${e.message}`); }
}

async function declineReq(id){
  try {
    await api(`/bookings/${id}/decline`,{method:"POST"});
    showToast("Request declined.");
    renderPending();
  } catch(e){ showToast(`⚠️ ${e.message}`); }
}

/* ---------- Upcoming Services ---------- */

async function renderUpcoming(){
  if(!guardPandit()) return;
  const strip=document.getElementById("upcoming-strip");
  const list =document.getElementById("upcoming-list");
  list.innerHTML=`<div class="empty"><div class="big">⏳</div><p>Loading…</p></div>`;
  const evts=await api("/me/upcoming").catch(e=>{ showToast("⚠️ "+e.message); return []; });
  calendarEvents=evts;  // cache for calendar
  const total=evts.reduce((s,e)=>s+e.price,0);
  strip.innerHTML=`<div class="earn-strip">
    <div class="es"><div class="v">${evts.length}</div><div class="k">Ceremonies booked</div></div>
    <div class="es"><div class="v">${fmt(total)}</div><div class="k">Expected dakshina</div></div>
  </div>`;
  list.innerHTML=evts.length ? evts.map(e=>`
    <div class="req-card">
      <div style="font-size:26px;width:52px;height:52px;border-radius:14px;background:var(--cream-warm);display:grid;place-items:center;flex-shrink:0">${SVC_ICONS[e.pooja_name]||"🪔"}</div>
      <div style="flex:1">
        <b style="font-family:'Marcellus',serif;font-size:17px;color:var(--maroon)">${e.pooja_name}</b>
        ${e.user_name?`<div style="font-size:13px;color:var(--ink-soft);margin-top:3px">for ${e.user_name}</div>`:""}
        <div style="font-size:12.5px;font-weight:700;color:var(--ink-soft);margin-top:4px">📅 ${reqWhen(e)}</div>
      </div>
      <div style="text-align:right">
        <div style="font-family:'Marcellus',serif;font-size:19px;color:var(--maroon)">${fmt(e.price)}</div>
        <span class="hstatus up">Confirmed</span>
      </div>
    </div>`).join("")
  : `<div class="empty"><div class="big">🗓</div><p>Nothing confirmed yet — accept requests from <b>Pending Requests</b> and they'll appear here.</p></div>`;
}

/* ---------- Calendar ---------- */

async function renderCalendar(){
  if(!guardPandit()) return;
  if(!calendarEvents.length){
    calendarEvents=await api("/me/upcoming").catch(()=>[]);
  }
  _drawCalendar();
}

function calShift(n){ calCursor=new Date(calCursor.getFullYear(),calCursor.getMonth()+n,1); _drawCalendar(); }
function calToday(){ calCursor=new Date(TODAY.getFullYear(),TODAY.getMonth(),1); renderCalendar(); }

function eventsOn(day){
  const k=dateKey(day);
  return calendarEvents.filter(e=>{
    const s=new Date(e.start_date+"T00:00:00"), end=new Date(e.end_date+"T00:00:00");
    return day>=s && day<=end;
  }).map(e=>({...e,isStart:e.start_date===k}));
}

function _drawCalendar(){
  document.getElementById("cal-title").textContent =
    calCursor.toLocaleDateString("en-IN",{month:"long",year:"numeric"});
  const firstDow=calCursor.getDay();
  const gridStart=addDays(calCursor,-firstDow);
  let html="";
  for(let i=0;i<42;i++){
    const day=addDays(gridStart,i);
    const inMonth=day.getMonth()===calCursor.getMonth();
    const isToday=dateKey(day)===dateKey(TODAY);
    const evts=eventsOn(day);
    let chips=evts.slice(0,3).map(e=>{
      const cls=e.duration_days?"multi":"booked";
      const txt=e.duration_days
        ? `${e.pooja_name}${e.isStart?"":" (contd.)"}`
        : `${(e.slots||[]).length===3?"Full day":(e.slots||[]).map(s=>s[0].toUpperCase()).join("/")} · ${e.pooja_name}`;
      return `<div class="cal-evt ${cls}" title="${e.pooja_name}${e.user_name?" — "+e.user_name:""} · ${fmt(e.price)}">${txt}</div>`;
    }).join("");
    if(evts.length>3) chips+=`<div class="cal-more">+${evts.length-3} more</div>`;
    html+=`<div class="cal-day ${inMonth?"":"other"} ${isToday?"is-today":""}">
      <div class="cd-num">${day.getDate()}</div>${chips}</div>`;
  }
  document.getElementById("cal-grid").innerHTML=html;
}

/* ---------- Add Service (post-enlist) ---------- */

function openAddSvc(){
  closeProfileMenu();
  customStaging=[];
  const offeredIds=new Set(PANDIT ? PANDIT.poojas.map(p=>String(p.service_id)) : []);
  const remaining=SERVICES.filter(s=>!offeredIds.has(String(s.id)));
  document.getElementById("addsvc-list").innerHTML=remaining.length
    ? remaining.map((s,i)=>svcPickRow(s,"as",i)).join("")
    : `<div class="muted-hint">You already offer everything in the catalogue — add something new below!</div>`;
  document.getElementById("addsvc-veil").classList.add("open");
  document.body.style.overflow="hidden";
}

function closeAddSvc(){ document.getElementById("addsvc-veil").classList.remove("open"); document.body.style.overflow=""; }

async function saveAddedServices(){
  const picked=collectPicked("as");
  const all=[...picked,...customStaging];
  if(!all.length){ showToast("⚠️ Tick a service and set a price, or add a new one."); return; }
  const ticked=document.querySelectorAll('[id^="as-pick-"].on').length;
  if(picked.length<ticked){ showToast("⚠️ Some ticked services are <b>missing a price</b>."); return; }
  try {
    for(const svc of picked){
      await api("/pandits/me/services",{method:"POST",body:JSON.stringify({service_id:svc.service_id,price:svc.price})});
    }
    for(const svc of customStaging){
      await api("/pandits/me/services/new",{method:"POST",body:JSON.stringify(svc)});
    }
    PANDIT=await api("/pandits/me");
    await refreshData();
    customStaging=[];
    closeAddSvc();
    showToast(`🪔 ${all.length} service${all.length>1?"s":""} added — live on your profile now.`);
  } catch(e){ showToast(`⚠️ Failed to save: <b>${e.message}</b>`); }
}


/* ============================================================
   INIT
   ============================================================ */

async function init(){
  renderAuthSlot();
  document.querySelector('.nav-link[data-page="home"]').classList.add("active");
  setMode("price");

  await Promise.all([restoreSession(), loadData()]);

  renderAuthSlot();
  renderLanding();
  document.getElementById("near-pooja").innerHTML =
    `<option value="">Any pooja</option>` + SERVICES.map(s=>`<option>${s.name}</option>`).join("");
}

init().catch(e => {
  console.error("Init failed:", e);
  showToast("⚠️ Could not connect to server. Is the backend running?");
});
