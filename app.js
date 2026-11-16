const DATA_URL = "data/lessons.json";
const DAYS = ["Poniedziałek","Wtorek","Środa","Czwartek","Piątek"];
const TEACHER_CODE_BY_SURNAME = {};
const state = { mode: "teacher", view: "list", lessons: [], changes: [], meta: {} };
const input = document.querySelector("#search-input");
const results = document.querySelector("#results");

const labels = {
  teacher: ["KOD NAUCZYCIELA","Np. Ga, Zi, WE…","Wpisz kod nauczyciela, np. Ga albo WE. Wyszukiwanie po inicjałach może być niedokładne — nie wszystkie nazwiska są przypisane do skrótów z planu.","Wyszukaj nauczyciela"],
  room: ["NUMER SALI","Np. 204, SG3, Aula…","Wpisz numer lub oznaczenie sali.","Wyszukaj salę"],
  class: ["ODDZIAŁ","Np. 4B, 2A…","Wpisz symbol klasy, np. 4B.","Wyszukaj klasę"]
};

function normalize(value){return String(value||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase().trim();}
function escapeHtml(value){return String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function setMode(mode){
  state.mode=mode;
  document.querySelectorAll(".tab").forEach(btn=>{
    const active=btn.dataset.mode===mode;
    btn.classList.toggle("active",active);btn.setAttribute("aria-selected",String(active));
  });
  const [label,placeholder,hint,title]=labels[mode];
  document.querySelector("#search-label").textContent=label;
  input.placeholder=placeholder;document.querySelector("#search-hint").textContent=hint;
  document.querySelector("#results-title").textContent=title;render();
}
document.querySelectorAll(".tab").forEach(btn=>btn.addEventListener("click",()=>setMode(btn.dataset.mode)));
document.querySelectorAll(".view-button").forEach(btn=>btn.addEventListener("click",()=>{
  state.view=btn.dataset.view;
  document.querySelectorAll(".view-button").forEach(button=>{
    const active=button.dataset.view===state.view;
    button.classList.toggle("active",active);
    button.setAttribute("aria-pressed",String(active));
  });
  render();
}));
input.addEventListener("input",render);
document.querySelector("#clear-btn").addEventListener("click",()=>{input.value="";input.focus();render();});

function render(){
  const query=normalize(input.value);
  if(!query){showEmpty("⌕","Wpisz kod, salę lub klasę","Wyniki pojawią się tutaj po wyszukaniu.");return;}
  const field=state.mode==="teacher"?"teacher":state.mode==="room"?"room":"class_name";
  const exactClassMatch=state.mode==="class"&&state.lessons.some(lesson=>normalize(lesson.class_name)===query);
  const matches=getScheduleGroups().map(group=>({group,rows:getResultRows(group,query,field,exactClassMatch)}))
    .filter(result=>result.rows.length)
    .sort((a,b)=>(a.group.lesson.day_index-b.group.lesson.day_index)||(a.group.lesson.lesson_number-b.group.lesson.lesson_number)||a.group.lesson.class_name.localeCompare(b.group.lesson.class_name));
  document.querySelector("#result-count").textContent=`${matches.length} ${plural(matches.length)}`;
  if(!matches.length){showEmpty("⌕","Brak wyników",state.lessons.length?"Nie znaleziono pasujących lekcji. Sprawdź wpisaną frazę.":"Baza nie zawiera jeszcze pobranych planów. Uruchom importer zgodnie z instrukcją README.");return;}
  results.classList.toggle("schedule-results",state.view==="table");
  results.innerHTML=state.view==="table"
    ?renderScheduleTable(matches)
    :matches.flatMap(result=>result.rows.map(row=>renderLesson(row.lesson,row.change,row.status,row))).join("");
}
function getResultRows(group,query,field,exactClassMatch){
  const rows=visibleRows(group);
  if(state.mode==="class"&&exactClassMatch){
    return normalize(group.lesson.class_name)===query?rows:[];
  }
  const matching=rows.filter(row=>matchesQuery(row.lesson,field,query));
  if(state.mode!=="room")return matching;
  const roomRows=matching.filter(row=>row.status!=="normal"||!isRoomUsedByReplacement(row.lesson));
  if(!group.change||group.change.action!=="replace")return roomRows;
  return roomRows.map(row=>{
    if(row.status==="replacement"){
      return{...row,displayTooltip:getRoomOccupancyTooltip(row.lesson,group)};
    }
    if(row.status==="cancelled"&&group.change.new_room&&group.change.new_room!==group.lesson.room){
      return{...row,displayTooltip:`Zajęcia przeniesiono do sali ${group.change.new_room}.`};
    }
    return row;
  });
}
function isRoomUsedByReplacement(lesson){
  const date=getWarsawDate();
  return state.changes.some(change=>change.date===date
    &&change.action==="replace"
    &&change.lesson_number===lesson.lesson_number
    &&change.new_room===lesson.room
    &&change.class_name!==lesson.class_name);
}
function visibleRows(group){
  const rows=groupRows(group);
  if(state.mode==="class"&&group.change?.action==="replace"){
    const replacement=rows.find(row=>row.status==="replacement");
    if(replacement){
      const tooltip=group.standalone
        ?`Informacja: ${group.change.original_text||describeLesson(replacement.lesson)}`
        :`Planowo: ${describeLesson(group.lesson)}`;
      return[{...replacement,status:"class-current",displayTooltip:tooltip}];
    }
  }
  if(state.mode!=="teacher"||!group.change)return rows;
  if(group.change.action==="cancel")return[];
  if(group.change.action==="replace"){
    const replacement=rows.find(row=>row.status==="replacement");
    if(group.change.new_teacher&&!group.standalone)return[{lesson:group.lesson,change:group.change,status:"absent"}];
    if(replacement)return[{...replacement,lesson:{...replacement.lesson,teacher:group.lesson.teacher}}];
  }
  return rows;
}
function matchesQuery(lesson,field,query){
  if(field!=="teacher")return normalize(lesson[field]).includes(query);
  const teacher=String(lesson.teacher||"");
  if(normalize(teacher).includes(query))return true;
  const surname=normalize(teacher).split(/[\s.]+/).filter(Boolean).pop();
  const code=Object.entries(TEACHER_CODE_BY_SURNAME).find(([name])=>normalize(name)===surname)?.[1];
  return Boolean(code&&normalize(code).includes(query));
}
function getScheduleGroups(){
  const groups=state.lessons.map(lesson=>({lesson,change:null}));
  const date=getWarsawDate();
  const dayIndex=getDayIndex(date);
  if(dayIndex<0)return groups;
  state.changes.filter(change=>change.date===date&&change.lesson_number!==null&&change.lesson_number!==undefined)
    .forEach(change=>{
      const affected=groups.filter(group=>!group.change&&group.lesson.class_name===change.class_name&&group.lesson.day_index===dayIndex&&group.lesson.lesson_number===change.lesson_number&&groupMatches(group.lesson,change.group));
      if(affected.length){
        affected.forEach(group=>group.change=change);
      }else if(change.action==="replace"){
        const time=state.lessons.find(lesson=>lesson.lesson_number===change.lesson_number)?.time||"";
        groups.push({lesson:{
          class_name:change.class_name,day_index:dayIndex,lesson_number:change.lesson_number,
          time,subject:change.new_subject||(change.moved?"Zajęcia przeniesione":"Zajęcia zastępcze"),
          teacher:change.new_teacher||"",room:change.new_room||"",group:change.group||""
        },change,standalone:true});
      }
    });
  return groups;
}
function groupMatches(lesson,group){
  if(!group)return true;
  const normalizeGroup=value=>normalize(value).replace(/^podzial\s*/, "");
  const wanted=normalizeGroup(group);
  const existing=normalizeGroup(lesson.group||"");
  if(wanted==="1"||wanted==="2")return existing===wanted||existing===`${wanted}/2`;
  return existing===wanted||normalize(lesson.subject).includes(wanted);
}
function groupRows(group){
  if(!group.change)return[{lesson:group.lesson,change:null,status:"normal"}];
  if(group.change.action==="cancel")return[{lesson:group.lesson,change:group.change,status:"cancelled"}];
  if(group.change.action!=="replace")return[{lesson:group.lesson,change:null,status:"normal"}];
  if(group.standalone)return[{lesson:group.lesson,change:group.change,status:"replacement"}];
  return[
    {lesson:group.lesson,change:group.change,status:"cancelled"},
    {lesson:{...group.lesson,subject:group.change.new_subject||group.lesson.subject,teacher:group.change.new_teacher||group.lesson.teacher,room:group.change.new_room||group.lesson.room},change:group.change,status:"replacement"}
  ];
}
function renderScheduleTable(resultsToRender){
  const rows=new Map();
  resultsToRender.forEach(({group,rows:matchingRows})=>{
    matchingRows.forEach(row=>{
      getScheduleEntries(group,row).forEach(entry=>{
      const lesson=entry.lesson;
      const key=`${lesson.lesson_number}|${lesson.time||""}`;
      if(!rows.has(key))rows.set(key,{lessonNumber:lesson.lesson_number,time:lesson.time||"",days:Array.from({length:5},()=>[])});
      rows.get(key).days[lesson.day_index].push(entry);
      });
    });
  });
  const sortedRows=[...rows.values()].sort((a,b)=>a.lessonNumber-b.lessonNumber||a.time.localeCompare(b.time));
  return`<p class="schedule-scroll-hint">Przesuń tabelę w bok, aby zobaczyć pozostałe dni.</p><div class="schedule-table-wrap"><table class="schedule-table">
    <thead><tr><th scope="col">Lekcja / godzina</th>${DAYS.map(day=>`<th scope="col">${escapeHtml(day)}</th>`).join("")}</tr></thead>
    <tbody>${sortedRows.map(row=>`<tr><th scope="row"><span>Lekcja ${escapeHtml(row.lessonNumber)}</span><small>${escapeHtml(row.time||"—")}</small></th>${row.days.map(entries=>`<td>${entries.map(renderScheduleEntry).join("")||"—"}</td>`).join("")}</tr>`).join("")}</tbody>
  </table></div>`;
}
function getScheduleEntries(group,row){
  const lesson=row.lesson;
  if(state.mode==="class"){
    const planned=lesson;
    if(!group.change)return[{lesson:planned,status:"normal",tooltip:""}];
    if(group.change.action==="replace"){
      if(row.status==="class-current"){
        const tooltip=group.standalone
          ?`Informacja: ${group.change.original_text||describeLesson(lesson)}`
          :`Planowo: ${describeLesson(group.lesson)}`;
        return[{lesson,status:"class-current",change:group.change,tooltip}];
      }
      if(group.standalone)return[{lesson:planned,status:"class-current",change:group.change,tooltip:`Informacja: ${group.change.original_text||describeLesson(planned)}`}];
      const replacement=groupRows(group).find(row=>row.status==="replacement");
      return[{lesson:planned,status:"planned-changed",change:group.change,tooltip:replacement?`Teraz: ${describeLesson(replacement.lesson)}`:"Lekcja zmieniona"}];
    }
    if(group.change.action==="cancel"){
      const notice=group.change.display_notice?`Informacja: ${group.change.original_text}`:"Lekcja odwołana";
      return[{lesson:planned,status:"cancelled",change:group.change,tooltip:notice}];
    }
    return[{lesson:planned,status:"normal",tooltip:""}];
  }
  if(state.mode==="teacher"){
    return [{
      lesson:row.lesson,
      status:row.status==="absent"?"absent":"normal",
      tooltip:row.status==="absent"?"Nieobecny":row.change?.new_room&&row.change.new_room!==group.lesson.room?`Nowa sala: ${row.change.new_room}`:"",
    }];
  }

  if(!group.change)return[{lesson,status:"normal",tooltip:""}];
  if(group.change.action==="cancel"){
    return[{lesson,status:"cancelled",change:group.change,tooltip:group.change.display_notice?`Informacja: ${group.change.original_text}`:"Lekcja odwołana"}];
  }
  if(group.change.action!=="replace")return[{lesson,status:"normal",tooltip:""}];

  if(row.status==="replacement"){
    const tooltip=row.displayTooltip||getRoomOccupancyTooltip(lesson,group);
    return[{lesson,status:"room-current",change:group.change,tooltip}];
  }
  if(row.status==="cancelled"&&group.change.new_room&&group.change.new_room!==group.lesson.room){
    return[{lesson,status:"moved-out",change:group.change,tooltip:row.displayTooltip||`Zajęcia przeniesiono do sali ${group.change.new_room}.`}];
  }
  return[{lesson,status:row.status,change:group.change,tooltip:row.displayTooltip||""}];
}
function getRoomOccupancyTooltip(replacement,group){
  const currentTeacher=replacement.teacher||"";
  const room=replacement.room||"";
  const occupants=state.lessons.filter(lesson=>lesson.day_index===replacement.day_index
    &&lesson.lesson_number===replacement.lesson_number
    &&lesson.room===room
    &&(group.lesson.room===room
      ||lesson.class_name!==group.lesson.class_name
      ||lesson.group!==group.lesson.group
      ||lesson.teacher!==group.lesson.teacher));
  const previousTeachers=[...new Set(occupants.map(lesson=>lesson.teacher).filter(Boolean))];
  if(previousTeachers.length){
    return`Zamiast ${previousTeachers.join(", ")} jest ${currentTeacher||"zastępstwo"}.`;
  }
  return`Sala ${room} była wolna. Teraz jest ${currentTeacher||"zastępstwo"}.`;
}
function describeLesson(lesson){
  return[lesson.subject,lesson.teacher,lesson.room?`sala ${lesson.room}`:""].filter(Boolean).join(" · ")||"Zajęcia";
}
function renderScheduleEntry(entry){
  const lesson=entry.lesson;
  const title=state.mode==="teacher"
    ?lesson.teacher||lesson.class_name
    :state.mode==="room"
      ?`${lesson.teacher||"Zajęcia"} · ${lesson.class_name}`
      :lesson.subject||"Zajęcia";
  const details=state.mode==="teacher"
    ?[lesson.class_name,lesson.room?`sala ${lesson.room}`:""].filter(Boolean).join(" · ")
    :state.mode==="room"
      ?[lesson.subject,lesson.group?`grupa ${lesson.group}`:""].filter(Boolean).join(" · ")
      :[lesson.class_name,lesson.teacher,lesson.room?`sala ${lesson.room}`:"",lesson.group?`grupa ${lesson.group}`:""].filter(Boolean).join(" · ");
  const tooltip=entry.tooltip||describeLesson(lesson);
  const notice=entry.change?.display_notice&&entry.status==="cancelled"?`<small class="schedule-notice">${escapeHtml(entry.change.original_text)}</small>`:"";
  return`<div class="schedule-entry schedule-${escapeHtml(entry.status)}" tabindex="0" title="${escapeHtml(tooltip)}" aria-label="${escapeHtml(tooltip)}">
    <span class="schedule-entry-title">${escapeHtml(title)}</span>${details?`<span class="schedule-entry-details">${escapeHtml(details)}</span>`:""}${state.mode==="room"&&entry.status==="room-current"?'<span class="schedule-entry-badge">Teraz</span>':""}${notice}
  </div>`;
}
function renderLesson(lesson,change,status,row){
  const day=DAYS[lesson.day_index]||lesson.day||"";
  const date=change?.date?` · ${escapeHtml(formatDate(change.date))}`:"";
  const badge=state.mode==="room"&&change?.action==="replace"
    ?status==="cancelled"?"Planowo":status==="replacement"?"Jest teraz":""
    :state.mode==="class"&&status==="class-current"?"Jest teraz"
    :state.mode==="teacher"&&status==="absent"?"Nieobecny"
    :status==="cancelled"?"Odwołano":status==="replacement"?(change.moved?"Przeniesiono":"Zastępstwo"):"";
  const roomNote=state.mode==="room"&&row?.displayTooltip?`<p class="change-note">${escapeHtml(row.displayTooltip)}</p>`:"";
  const note=roomNote||(change?.original_text&&status!=="absent"&&(status!=="cancelled"||change.display_notice)?`<p class="change-note">${status==="cancelled"?"Informacja: ":"Zmiana: "}${escapeHtml(change.original_text)}</p>`:"");
  const subject=state.mode==="teacher"&&(status==="replacement"||status==="absent")?"":`<strong>${escapeHtml(lesson.subject||"Zajęcia")}</strong>`;
  return`<article class="lesson-card${status==="cancelled"?" lesson-cancelled":""}${status==="replacement"?" lesson-replacement":""}${status==="class-current"?" lesson-class-current":""}"${row?.displayTooltip?` title="${escapeHtml(row.displayTooltip)}"`:""}>
      <div class="lesson-time">${escapeHtml(lesson.time||"—")}<small>${escapeHtml(day)}${date}, lekcja ${escapeHtml(lesson.lesson_number)}</small></div>
      <div class="lesson-main">${subject}${badge?`<span class="change-badge${status==="absent"?" absence-badge":""}">${escapeHtml(badge)}</span>`:""}<p>${escapeHtml(lesson.teacher||"Brak nauczyciela")} · ${escapeHtml(lesson.class_name)}${lesson.group?` · grupa ${escapeHtml(lesson.group)}`:""}</p>${note}</div>
      <div class="lesson-room">${escapeHtml(lesson.room||"Brak sali")}</div>
    </article>`;
}
function getWarsawDate(){
  const parts=new Intl.DateTimeFormat("en-CA",{timeZone:"Europe/Warsaw",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date());
  const values=Object.fromEntries(parts.map(part=>[part.type,part.value]));
  return`${values.year}-${values.month}-${values.day}`;
}
function getDayIndex(date){
  const day=new Date(`${date}T00:00:00Z`).getUTCDay();
  return day>=1&&day<=5?day-1:-1;
}
function formatDate(date){
  const [year,month,day]=date.split("-");
  return`${day}.${month}.${year}`;
}
function plural(n){if(n===1)return"lekcja";if(n%10>=2&&n%10<=4&&(n%100<12||n%100>14))return"lekcje";return"lekcji";}
function showEmpty(icon,title,description){
  results.classList.remove("schedule-results");
  document.querySelector("#result-count").textContent="—";
  results.innerHTML=`<div class="empty-state"><div class="empty-icon">${icon}</div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(description)}</p></div>`;
}
async function loadData(){
  try{
    const response=await fetch(`${DATA_URL}?v=${Date.now()}`,{cache:"no-store"});
    if(!response.ok)throw new Error("Nie udało się pobrać bazy");
    const data=await response.json();
    state.lessons=Array.isArray(data.lessons)?data.lessons:[];
    state.changes=Array.isArray(data.changes)?data.changes:[];
    state.meta=data.meta||{};
    const updatedAt=new Date(state.meta.updated_at||"");
    const timestamp=Number.isNaN(updatedAt.getTime())
      ?"brak informacji"
      :new Intl.DateTimeFormat("pl-PL",{timeZone:"Europe/Warsaw",dateStyle:"short",timeStyle:"short"}).format(updatedAt);
    document.querySelector("#sync-label").textContent=`Ostatnia synchronizacja: ${timestamp}`;
    render();
  }catch(error){
    document.querySelector("#sync-label").textContent="Nie udało się wczytać danych";
    showEmpty("!","Nie można wczytać bazy","Sprawdź, czy aplikacja została opublikowana razem z folderem data.");
  }
}
loadData();
