import streamlit as st
import pandas as pd
import pymssql
import matplotlib.pyplot as plt
import tempfile
import os
import calendar
import warnings
from fpdf import FPDF
from datetime import datetime

warnings.filterwarnings('ignore')

# Configuración de la página de Streamlit
st.set_page_config(page_title="Generador de Reportes Productivos - FAMMA", layout="wide")

# ==========================================
# 1. DICCIONARIO FAMMA
# ==========================================
MAQUINAS_MAP = {
    # --- ESTAMPADO ---
    "LINEA 1.2": "LINEA 1.2", "LINEA 1.4": "LINEA 1.4", "LINEA 1.5": "LINEA 1.5",
    "LINEA 2": "LINEA 2", "LINEA 3": "LINEA 3", "LINEA 4": "LINEA 4", "RETRABAJO": "RETRABAJO",

    # --- SOLDADURA ---
    "Cell 1 Famma": "CELDAS", "Cell 2 Famma": "CELDAS", "Cell 3 Famma": "CELDAS",
    "Cell 4 Famma": "CELDAS", "Cell 5 Famma": "CELDAS", "Cell 6 Famma": "CELDAS",
    "Cell 7  Famma": "CELDAS", "Cell 8 Famma": "CELDAS", "Cell 9 Famma": "CELDAS",
    "Cell 10 Famma": "CELDAS", "Cell 11 Famma": "CELDAS", "Cell 12 Famma": "CELDAS",
    "Cell 13 Famma": "CELDAS", "Cell 14 Famma": "CELDAS", "Cell 15A Famma": "CELDAS",
    "Cell 15B Famma": "CELDAS", "Cell 16 Famma": "CELDAS", "Cell 17 Famma": "CELDAS",

    "PRP 1": "PRP", "PRP 2": "PRP", "PRP 3": "PRP", 
    "PRP 4": "PRP", "PRP 5": "PRP", "PRP 6": "PRP",

    "MIG 1": "MIG", "MIG 2": "MIG",
    
    "PIN 1003 - 2": "PIN", "PIN 1486 - 5": "PIN", "PIN 313 - 4": "PIN", 
    "PIN 3288 - 6": "PIN", "PIN 3344 - 3": "PIN", "PIN 794 - 7": "PIN", "PIN 806 - 1": "PIN",
    
    "Pegado Tape": "OTROS"
}

GRUPOS_ESTAMPADO = ['LINEA 1.2', 'LINEA 1.4', 'LINEA 1.5', 'LINEA 2', 'LINEA 3', 'LINEA 4', 'RETRABAJO']
GRUPOS_SOLDADURA = ['CELDAS', 'PRP', 'MIG', 'PIN', 'OTROS']

# ==========================================
# 2. HERRAMIENTAS Y PDF
# ==========================================
class ReportePDF(FPDF):
    def __init__(self, area, fecha_str, theme_color):
        super().__init__()
        self.area = area; self.fecha_str = fecha_str; self.theme_color = theme_color

    def add_gradient_background(self):
        self.set_fill_color(230, 233, 238)
        self.rect(0, 0, self.w, self.h, 'F')

    def rounded_rect(self, x, y, w, h, r, style=''):
        k = self.k; hp = self.h
        op = 'f' if style == 'F' else 'B' if style in ['FD', 'DF'] else 'S'
        MyArc = 4/3 * ((2 ** 0.5) - 1)
        self._out(f'{(x + r) * k:.2f} {(hp - y) * k:.2f} m')
        xc = x + w - r; yc = y + r
        self._out(f'{xc * k:.2f} {(hp - y) * k:.2f} l')
        self._out(f'{(xc + r * MyArc) * k:.2f} {(hp - y) * k:.2f} {(x + w) * k:.2f} {(hp - yc + r * MyArc) * k:.2f} {(x + w) * k:.2f} {(hp - yc) * k:.2f} c')
        yc = y + h - r
        self._out(f'{(x + w) * k:.2f} {(hp - yc) * k:.2f} l')
        self._out(f'{(x + w) * k:.2f} {(hp - yc - r * MyArc) * k:.2f} {(xc + r * MyArc) * k:.2f} {(hp - y - h) * k:.2f} {xc * k:.2f} {(hp - y - h) * k:.2f} c')
        xc = x + r
        self._out(f'{xc * k:.2f} {(hp - y - h) * k:.2f} l')
        self._out(f'{(xc - r * MyArc) * k:.2f} {(hp - y - h) * k:.2f} {x * k:.2f} {(hp - yc - r * MyArc) * k:.2f} {x * k:.2f} {(hp - yc) * k:.2f} c')
        yc = y + r
        self._out(f'{x * k:.2f} {(hp - yc) * k:.2f} l')
        self._out(f'{x * k:.2f} {(hp - yc + r * MyArc) * k:.2f} {(xc - r * MyArc) * k:.2f} {(hp - y) * k:.2f} {xc * k:.2f} {(hp - y) * k:.2f} c')
        self._out(op)

    def draw_panel(self, x, y, w, h, r=3, bg_color=(255,255,255)):
        self.set_fill_color(200, 204, 210); self.rounded_rect(x + 1.5, y + 1.5, w, h, r, style='F')
        self.set_fill_color(*bg_color); self.set_draw_color(200, 204, 210); self.rounded_rect(x, y, w, h, r, style='DF')

def save_chart_mpl(fig):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        fig.savefig(tmp.name, format='jpeg', facecolor='white', dpi=250)
        plt.close(fig)
        return tmp.name

# ==========================================
# 3. EXTRACCIÓN DE BASE DE DATOS
# ==========================================
def fetch_data_from_db(fecha_ini, fecha_fin, mes, anio):
    try:
        conexion = pymssql.connect(
            server=st.secrets['WIIDEM_SERVER'],
            user=st.secrets['WIIDEM_USER'],
            password=st.secrets['WIIDEM_PASS'],
            database=st.secrets['WIIDEM_DB'],
            login_timeout=15
        )
        q_trend = f"SELECT p.Month, c.Name as Máquina, SUM(COALESCE(p.Good, 0)) as Buenas, SUM(COALESCE(p.Rework, 0)) as Retrabajo, SUM(COALESCE(p.Scrap, 0)) as Observadas, SUM(COALESCE(p.Good, 0) + COALESCE(p.Rework, 0) + COALESCE(p.Scrap, 0)) as Totales FROM PROD_M_03 p JOIN CELL c ON p.CellId = c.CellId WHERE p.Year = {anio} AND p.Month <= {mes} GROUP BY p.Month, c.Name"
        q_piezas = f"SELECT c.Name as Máquina, COALESCE(pr.Code, 'S/C') as Pieza, SUM(COALESCE(p.Scrap, 0)) as Scrap, SUM(COALESCE(p.Rework, 0)) as RT FROM PROD_M_01 p JOIN CELL c ON p.CellId = c.CellId LEFT JOIN PRODUCT pr ON p.ProductId = pr.ProductId WHERE p.Year = {anio} AND p.Month = {mes} GROUP BY c.Name, pr.Code"

        df_piezas = pd.read_sql(q_piezas, conexion).fillna(0)
        df_trend = pd.read_sql(q_trend, conexion).fillna(0)
        conexion.close()

        for col in ['Month', 'Buenas', 'Retrabajo', 'Observadas', 'Totales']:
            if col in df_trend.columns: df_trend[col] = pd.to_numeric(df_trend[col], errors='coerce').fillna(0)
        return df_trend, df_piezas
    except Exception as e:
        st.error(f"Error de conexión SQL: {e}")
        return pd.DataFrame(), pd.DataFrame()

# ==========================================
# 4. MOTOR INFORME PRODUCTIVO
# ==========================================
def crear_pdf_informe_productivo(area, label_reporte, df_trend, df_piezas, mes_sel, anio_sel, hs_rt):
    theme_color = (15, 76, 129) if area.upper() == "ESTAMPADO" else (211, 84, 0)
    theme_hex = '#%02x%02x%02x' % theme_color
    color_target_fail = '#E74C3C'
    scrap_c = '#0f4c81' if area.upper() == "ESTAMPADO" else '#D35400'
    rt_c = theme_hex
    grupos = GRUPOS_ESTAMPADO if area.upper() == "ESTAMPADO" else GRUPOS_SOLDADURA
    pdf = ReportePDF(f"INFORME PRODUCTIVO - {area}", label_reporte, theme_color)
    
    mapa_limpio = {str(k).strip(): str(v).strip().upper() for k, v in MAQUINAS_MAP.items()}
    df_t = df_trend.copy(); df_p = df_piezas.copy()

    for d in [df_t, df_p]:
        if not d.empty and 'Máquina' in d.columns:
            d['Grupo'] = d['Máquina'].astype(str).str.strip().map(mapa_limpio).fillna('Otro')
        else: d['Grupo'] = 'Otro'

    df_t = df_t[df_t['Grupo'].isin(grupos)]; df_p = df_p[df_p['Grupo'].isin(grupos)]
    paginas = ['GENERAL'] + [g for g in grupos if g in df_t['Grupo'].unique()]
    
    target_scrap = 0.50 if area.upper() == "ESTAMPADO" else 0.30
    target_rt = 2.00

    def format_qty(val):
        if val >= 1000000: return f"{val/1000000:.2f}M"
        elif val >= 100000: return f"{val/1000:.0f}k"
        elif val >= 1000: return f"{val/1000:.2f}k"
        return str(int(val))

    for target in paginas:
        pdf.add_page(orientation='L'); pdf.set_auto_page_break(False); pdf.add_gradient_background()
        if target == 'GENERAL': df_t_target = df_t; df_p_target = df_p
        else: df_t_target = df_t[df_t['Grupo'] == target]; df_p_target = df_p[df_p['Grupo'] == target]

        pdf.set_y(8); pdf.set_fill_color(*theme_color); pdf.set_text_color(255); pdf.set_font("Arial", 'B', 10)
        pdf.cell(40, 6, f"PERIODO: {mes_sel}/{anio_sel}", 1, 0, 'C', fill=True)
        pdf.cell(197, 6, f"PLANTA {area.upper()} - {target}", 1, 0, 'C', fill=True)
        pdf.cell(40, 6, "PRODUCTIVO", 1, 1, 'C', fill=True)

        if df_t_target.empty: continue

        for col in ['Buenas', 'Observadas', 'Retrabajo', 'Totales']:
            if col in df_t_target.columns: df_t_target[col] = pd.to_numeric(df_t_target[col], errors='coerce').fillna(0)

        df_ev = df_t_target.groupby('Month')[['Buenas', 'Observadas', 'Retrabajo', 'Totales']].sum().reset_index()
        if 'Month' in df_ev.columns: df_ev['Month'] = df_ev['Month'].astype(int)
        df_ev['Totales_Div'] = df_ev['Totales'].apply(lambda x: x if x > 0 else 1)
        df_ev['% Scrap'] = ((df_ev['Observadas'] / df_ev['Totales_Div']) * 100).round(2)
        df_ev['% RT'] = ((df_ev['Retrabajo'] / df_ev['Totales_Div']) * 100).round(2)
        df_ev['Mes_Str'] = df_ev['Month'].map({1:'Ene', 2:'Feb', 3:'Mar', 4:'Abr', 5:'May', 6:'Jun', 7:'Jul', 8:'Ago', 9:'Sep', 10:'Oct', 11:'Nov', 12:'Dic'})

        h_box = 58
        pdf.draw_panel(10, 18, 135, h_box); pdf.draw_panel(10, 79, 135, h_box); pdf.draw_panel(10, 140, 135, h_box)
        pdf.set_font("Arial", 'B', 9); pdf.set_text_color(15, 45, 80)
        pdf.set_xy(10, 22); pdf.cell(135, 5, "PIEZAS TOTALES", 0, 0, 'C')
        pdf.set_xy(10, 83); pdf.cell(135, 5, "% SCRAP", 0, 0, 'C')
        pdf.set_xy(10, 144); pdf.cell(135, 5, "% RE-TRABAJO", 0, 0, 'C')

        def plot_trend_left(col_y, target_val=None, is_pct=False):
            fig, ax = plt.subplots(figsize=(5.1, 1.8))
            colors = [color_target_fail if (is_pct and val > target_val) else theme_hex for val in df_ev[col_y]]
            bars = ax.bar(df_ev['Mes_Str'], df_ev[col_y], color=colors, edgecolor='white', width=0.65)
            max_y = df_ev[col_y].max()
            if target_val is not None: max_y = max(max_y, target_val)
            ax.set_ylim(0, max_y * 1.45 if max_y > 0 else 1); ax.set_xlim(-0.8, len(df_ev) + 0.2)
            if target_val is not None:
                ax.axhline(y=target_val, color='#E74C3C', linestyle='--', linewidth=1.5, alpha=0.7)
                ax.text(len(df_ev) - 0.5, target_val + (max_y*0.05), f'Obj: {target_val}%', color='#555555', fontsize=8, ha='center', fontweight='bold')
            for bar in bars:
                yval = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2.0, yval + (max_y*0.03), f"{yval:.2f}%" if is_pct else format_qty(yval), ha='center', va='bottom', rotation=0, fontsize=8.5, fontweight='bold', color='#111111')
            for spine in ax.spines.values(): spine.set_visible(False)
            ax.yaxis.set_visible(False); ax.tick_params(axis='x', bottom=False, labelsize=8, labelcolor='#111111')
            fig.subplots_adjust(left=0.02, right=0.98, top=0.90, bottom=0.18)
            return fig

        f1 = plot_trend_left('Totales'); f1.set_size_inches(5.1, 1.8); i1 = save_chart_mpl(f1); pdf.image(i1, x=13.5, y=28, w=128); os.remove(i1)
        f2 = plot_trend_left('% Scrap', target_scrap, True); f2.set_size_inches(5.1, 1.8); i2 = save_chart_mpl(f2); pdf.image(i2, x=13.5, y=89, w=128); os.remove(i2)
        f3 = plot_trend_left('% RT', target_rt, True); f3.set_size_inches(5.1, 1.8); i3 = save_chart_mpl(f3); pdf.image(i3, x=13.5, y=150, w=128); os.remove(i3)

        h_br = 84
        pdf.draw_panel(150, 18, 135, h_br); pdf.draw_panel(150, 105, 135, h_br)
        pdf.set_font("Arial", 'B', 9); pdf.set_text_color(15, 45, 80)
        pdf.set_xy(150, 22); pdf.cell(135, 5, "TOP 5 SCRAP", 0, 0, 'C')
        pdf.set_xy(150, 109); pdf.cell(135, 5, "TOP 5 RT", 0, 0, 'C')

        if not df_p_target.empty:
            t_s = df_p_target.groupby('Pieza')['Scrap'].sum().nlargest(5).reset_index().sort_values('Scrap', ascending=True)
            t_rt = df_p_target.groupby('Pieza')['RT'].sum().nlargest(5).reset_index().sort_values('RT', ascending=True)

            def plot_top5(df_data, col_x, bar_color):
                fig, ax = plt.subplots(figsize=(5.1, 2.8))
                if df_data.empty or df_data[col_x].sum() == 0:
                    ax.text(0.5, 0.5, "Sin datos", ha='center', va='center', fontsize=10); ax.axis('off'); return fig
                bars = ax.barh(df_data['Pieza'], df_data[col_x], color=bar_color, edgecolor='white', height=0.7)
                for spine in ax.spines.values(): spine.set_visible(False)
                ax.xaxis.set_visible(False); ax.tick_params(axis='y', length=0, labelsize=8)
                max_x = df_data[col_x].max(); ax.set_xlim(0, max_x * 1.35 if max_x > 0 else 1); ax.set_ylim(-0.5, len(df_data) - 0.5)
                for bar in bars:
                    width = bar.get_width()
                    ax.text(width + (max_x*0.02), bar.get_y() + bar.get_height()/2, f"{int(width):,}".replace(",", "."), ha='left', va='center', fontsize=9, fontweight='bold', color='#111111')
                fig.subplots_adjust(left=0.35, right=0.90, top=0.95, bottom=0.05); return fig

            f4 = plot_top5(t_s, 'Scrap', scrap_c); f4.set_size_inches(5.1, 2.8); i4 = save_chart_mpl(f4); pdf.image(i4, x=153.5, y=28, w=128); os.remove(i4)
            f5 = plot_top5(t_rt, 'RT', rt_c); f5.set_size_inches(5.1, 2.8); i5 = save_chart_mpl(f5); pdf.image(i5, x=153.5, y=115, w=128); os.remove(i5)

        if target == 'GENERAL' and area.upper() == 'ESTAMPADO':
            hs_val = hs_rt if hs_rt is not None else 0.0
            pdf.draw_panel(150, 192, 135, 12, 3, (245,245,245)); pdf.set_font("Arial", 'B', 10); pdf.set_xy(150, 192); pdf.set_text_color(0)
            pdf.cell(80, 12, "HS RE-TRABAJO TOTAL: ", 0, 0, 'R'); pdf.set_text_color(*theme_color); pdf.cell(40, 12, f"{hs_val:.1f} hs", 0, 0, 'C')

    return pdf.output(dest='S').encode('latin-1')


# ==========================================
# 5. INTERFAZ Y LÓGICA DE STREAMLIT
# ==========================================

# Variables de sesión para PDFs
if 'pdf_est_famma' not in st.session_state:
    st.session_state.pdf_est_famma = None
if 'pdf_sol_famma' not in st.session_state:
    st.session_state.pdf_sol_famma = None
if 'last_mes_famma' not in st.session_state:
    st.session_state.last_mes_famma = None
if 'last_anio_famma' not in st.session_state:
    st.session_state.last_anio_famma = None

# Variables de sesión para Inputs
hoy = datetime.now()
if 'input_mes' not in st.session_state:
    st.session_state.input_mes = hoy.month
if 'input_anio' not in st.session_state:
    st.session_state.input_anio = hoy.year

st.title("🏭 Generador de Reportes Productivos - FAMMA")
st.markdown("Selecciona los parámetros para extraer los datos de Wiidem y generar los PDFs de FAMMA.")

with st.sidebar:
    st.header("Parámetros del Reporte")
    # Usamos 'key' para que Streamlit ate permanentemente el widget al valor en memoria
    mes = st.number_input("Mes", min_value=1, max_value=12, value=st.session_state.input_mes, key="input_mes")
    anio = st.number_input("Año", min_value=2000, max_value=2100, value=st.session_state.input_anio, key="input_anio")
    hs_rt_manual = st.number_input("Horas de Re-trabajo (Estampado)", min_value=0.0, value=0.0, step=1.0, key="input_hs")
    
    generar_btn = st.button("Generar Reportes FAMMA", type="primary")

if generar_btn:
    label = f"{mes}/{anio}"
    
    with st.spinner("Consultando servidor Wiidem de FAMMA..."):
        fecha_ini = pd.to_datetime(f"{anio}-{mes}-01")
        fecha_fin = pd.to_datetime(f"{anio}-{mes}-{calendar.monthrange(anio, mes)[1]}")
        
        df_t, df_p = fetch_data_from_db(fecha_ini, fecha_fin, mes, anio)
        
    if not df_t.empty:
        with st.spinner("Renderizando PDF de Estampado..."):
            st.session_state.pdf_est_famma = crear_pdf_informe_productivo("ESTAMPADO", label, df_t, df_p, mes, anio, hs_rt_manual)
            
        with st.spinner("Renderizando PDF de Soldadura..."):
            st.session_state.pdf_sol_famma = crear_pdf_informe_productivo("SOLDADURA", label, df_t, df_p, mes, anio, hs_rt_manual)
            
        st.session_state.last_mes_famma = mes
        st.session_state.last_anio_famma = anio
    else:
        st.error("⚠️ No se encontraron datos para ese mes o falló la conexión al servidor de FAMMA.")
        st.session_state.pdf_est_famma = None
        st.session_state.pdf_sol_famma = None

if st.session_state.pdf_est_famma is not None and st.session_state.pdf_sol_famma is not None:
    st.success("✅ Datos extraídos correctamente. Archivos PDF listos para descargar:")
    
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="📄 Descargar Reporte ESTAMPADO",
            data=st.session_state.pdf_est_famma,
            file_name=f"FAMMA_PROD_ESTAMPADO_{st.session_state.last_mes_famma}_{st.session_state.last_anio_famma}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
        
    with col2:
        st.download_button(
            label="📄 Descargar Reporte SOLDADURA",
            data=st.session_state.pdf_sol_famma,
            file_name=f"FAMMA_PROD_SOLDADURA_{st.session_state.last_mes_famma}_{st.session_state.last_anio_famma}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
