
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO

# =========================================================
# 1. CONFIGURACIÓN GENERAL
# =========================================================
st.set_page_config(
    page_title="Control de Inventarios | Agrícola Progreso",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
# 2. CSS: CORRECCIÓN DEL TÍTULO RECORTADO
# =========================================================
st.markdown("""
<style>
    /* Espacio superior para evitar que el contenido se corte */
    .block-container {
        padding-top: 3rem !important;
        padding-bottom: 2rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }

    /* Título principal personalizado */
    .main-title {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 12px;
        width: 100%;
        box-sizing: border-box;
        margin-top: 1rem;
        margin-bottom: 1.5rem;
        padding: 0.8rem 0.3rem 1rem 0.3rem;
        line-height: 1.5;
        overflow: visible;
        font-size: clamp(1.5rem, 3vw, 2.4rem);
        font-weight: 750;
    }

    .main-title .title-icon {
        display: inline-block;
        flex-shrink: 0;
        line-height: 1.4;
        padding: 0.1rem;
    }

    /* Encabezados sin recortes */
    h1, h2, h3 {
        line-height: 1.4 !important;
        overflow-wrap: anywhere;
    }

    h1 {
        padding-top: 0.3rem !important;
        margin-top: 0.5rem !important;
    }

    /* Tarjetas de indicadores */
    div[data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.08);
        border: 1px solid rgba(128, 128, 128, 0.18);
        padding: 16px;
        border-radius: 12px;
    }

    /* Botones */
    div.stDownloadButton button,
    div.stButton button {
        border-radius: 8px;
    }

    /* Tablas */
    div[data-testid="stDataFrame"] {
        width: 100%;
    }

    @media (max-width: 768px) {
        .block-container {
            padding-top: 2rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }

        .main-title {
            font-size: 1.5rem;
            gap: 8px;
        }
    }
</style>
""", unsafe_allow_html=True)


# =========================================================
# 3. EMPRESA Y DATOS BASE
# =========================================================
EMPRESA = "COMERCIAL AGRÍCOLA PROGRESO S.A.C."

COLUMNAS = [
    "producto",
    "familia",
    "precio_unit",
    "stock_actual",
    "demanda_mensual_jun",
    "demanda_mensual_jul",
    "demanda_mensual_ago",
    "lead_time_dias",
    "sigma_lt"
]

DATOS_DEMO = pd.DataFrame([
    {
        "producto": "Fertilizante NPK",
        "familia": "Linea 1",
        "precio_unit": 85,
        "stock_actual": 120,
        "demanda_mensual_jun": 180,
        "demanda_mensual_jul": 210,
        "demanda_mensual_ago": 195,
        "lead_time_dias": 7,
        "sigma_lt": 1.5
    },
    {
        "producto": "Semillas certificadas",
        "familia": "Linea 2",
        "precio_unit": 45,
        "stock_actual": 75,
        "demanda_mensual_jun": 100,
        "demanda_mensual_jul": 120,
        "demanda_mensual_ago": 110,
        "lead_time_dias": 5,
        "sigma_lt": 1.0
    },
    {
        "producto": "Insumo agrícola C",
        "familia": "Linea 3",
        "precio_unit": 60,
        "stock_actual": 40,
        "demanda_mensual_jun": 90,
        "demanda_mensual_jul": 105,
        "demanda_mensual_ago": 120,
        "lead_time_dias": 10,
        "sigma_lt": 2.0
    }
])


# =========================================================
# 4. FUNCIONES DE VALIDACIÓN Y CÁLCULO
# =========================================================
def validar_datos(datos):
    df = datos.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]

    faltantes = [c for c in COLUMNAS if c not in df.columns]

    if faltantes:
        raise ValueError(
            "Faltan estas columnas en el Excel: "
            + ", ".join(faltantes)
        )

    df = df[COLUMNAS].copy()

    # Eliminar filas completamente vacías o sin producto
    df = df.dropna(how="all")
    df = df.dropna(subset=["producto"])

    if df.empty:
        raise ValueError("No hay productos para analizar.")

    df["producto"] = df["producto"].astype(str).str.strip()
    df["familia"] = df["familia"].fillna("").astype(str).str.strip()

    if (df["producto"] == "").any():
        raise ValueError("Hay productos sin nombre.")

    if (df["familia"] == "").any():
        raise ValueError("Todos los productos deben tener una familia.")

    if df["producto"].duplicated().any():
        raise ValueError(
            "Hay nombres de productos duplicados. "
            "Usa un nombre único para cada producto."
        )

    familias = df["familia"].nunique()

    if familias > 3:
        raise ValueError(
            f"Se encontraron {familias} familias. "
            "Esta aplicación está configurada para un máximo de 3 líneas."
        )

    columnas_numericas = [c for c in COLUMNAS if c not in ["producto", "familia"]]

    for col in columnas_numericas:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if df[columnas_numericas].isna().any().any():
        raise ValueError(
            "Hay valores numéricos vacíos o inválidos. "
            "Revisa precios, stock, demanda, tiempo de entrega y sigma_lt."
        )

    if not np.isfinite(df[columnas_numericas].to_numpy(dtype=float)).all():
        raise ValueError("Los datos numéricos deben ser valores finitos.")

    if (df[columnas_numericas] < 0).any().any():
        raise ValueError("No se permiten valores numéricos negativos.")

    if (df["lead_time_dias"] <= 0).any():
        raise ValueError("El tiempo de entrega debe ser mayor que cero.")

    return df


def calcular_inventario(datos, nivel_servicio):
    df = validar_datos(datos)

    # Factores Z aproximados para distintos niveles de servicio
    factores_z = {
        90: 1.282,
        95: 1.645,
        97.5: 1.960,
        99: 2.326
    }
    z = factores_z[nivel_servicio]

    meses = [
        "demanda_mensual_jun",
        "demanda_mensual_jul",
        "demanda_mensual_ago"
    ]

    # Indicadores de demanda
    df["demanda_prom"] = df[meses].mean(axis=1)

    # Desviación estándar muestral de la demanda mensual
    df["sigma_mensual"] = df[meses].std(axis=1, ddof=1).fillna(0)

    # Valor anual estimado de la demanda
    df["valor_anual"] = (
        df["demanda_prom"] * 12 * df["precio_unit"]
    )

    # Análisis ABC según valor anual
    df = df.sort_values("valor_anual", ascending=False).reset_index(drop=True)

    total_valor = df["valor_anual"].sum()

    if total_valor > 0:
        df["pct_valor"] = df["valor_anual"] / total_valor
        df["pct_acum"] = df["pct_valor"].cumsum()

        # El producto que cruza un umbral completa esa categoría
        acumulado_anterior = df["pct_acum"].shift(1, fill_value=0)

        df["clase"] = np.select(
            [
                acumulado_anterior < 0.80,
                acumulado_anterior < 0.95
            ],
            ["A", "B"],
            default="C"
        )
    else:
        df["pct_valor"] = 0.0
        df["pct_acum"] = 0.0
        df["clase"] = "C"

    # Demanda diaria estimada
    df["demanda_diaria"] = df["demanda_prom"] / 30

    # Supuesto: demanda diaria independiente y estable
    df["sigma_diaria"] = df["sigma_mensual"] / np.sqrt(30)

    # Stock de seguridad
    var_demanda_lt = (
        df["lead_time_dias"] * df["sigma_diaria"] ** 2
    )
    var_plazo_entrega = (
        df["demanda_diaria"] ** 2 * df["sigma_lt"] ** 2
    )

    df["SS"] = np.ceil(
        z * np.sqrt(var_demanda_lt + var_plazo_entrega)
    ).astype(int)

    # Punto de reposición
    df["ROP"] = np.ceil(
        df["demanda_diaria"] * df["lead_time_dias"] + df["SS"]
    ).astype(int)

    # Alertas y sugerencias
    df["stock_disponible"] = df["stock_actual"] - df["ROP"]

    df["estado_stock"] = np.where(
        df["stock_actual"] <= df["ROP"],
        "Reponer",
        "Stock suficiente"
    )

    df["reponer_unidades"] = np.maximum(
        df["ROP"] - df["stock_actual"], 0
    ).astype(int)

    df["valor_inventario"] = df["stock_actual"] * df["precio_unit"]

    return df


def crear_excel(df):
    salida = BytesIO()

    with pd.ExcelWriter(salida, engine="openpyxl") as writer:
        df.to_excel(
            writer,
            index=False,
            sheet_name="Inventario"
        )

    salida.seek(0)
    return salida.getvalue()


def formato_dinero(valor):
    return f"S/ {valor:,.2f}"


# =========================================================
# 5. CARGA INICIAL Y CONFIGURACIÓN
# =========================================================
if "datos_inventario" not in st.session_state:
    st.session_state["datos_inventario"] = DATOS_DEMO.copy()

if "nombre_archivo" not in st.session_state:
    st.session_state["nombre_archivo"] = "Datos demostrativos"

if "nivel_servicio" not in st.session_state:
    st.session_state["nivel_servicio"] = 95


# =========================================================
# 6. MENÚ LATERAL
# =========================================================
with st.sidebar:
    st.markdown(f"### 🏢 {EMPRESA}")
    st.caption("Sistema de gestión y control de inventarios")
    st.divider()

    pagina = st.radio(
        "NAVEGACIÓN",
        [
            "Dashboard Gerencial",
            "Cargar Excel",
            "Base de Datos",
            "Indicadores de Demanda",
            "Análisis ABC",
            "Stock de Seguridad y ROP",
            "Reporte Final"
        ]
    )

    st.divider()

    nivel_servicio = st.selectbox(
        "Nivel de servicio",
        options=[90, 95, 97.5, 99],
        index=[90, 95, 97.5, 99].index(
            st.session_state["nivel_servicio"]
        ),
        format_func=lambda x: f"{x}%"
    )

    st.session_state["nivel_servicio"] = nivel_servicio

    st.caption("Los datos demostrativos pueden reemplazarse con un archivo Excel.")


# =========================================================
# 7. PROCESAMIENTO DE DATOS
# =========================================================
try:
    df = calcular_inventario(
        st.session_state["datos_inventario"],
        st.session_state["nivel_servicio"]
    )
except Exception as e:
    st.error(f"No se pudieron procesar los datos: {e}")
    st.stop()


# =========================================================
# 8. ENCABEZADO GENERAL
# =========================================================
st.markdown(
    """
    <div class="main-title">
        <span class="title-icon">📦</span>
        <span>Gestión y Control de Inventarios</span>
    </div>
    """,
    unsafe_allow_html=True
)

st.caption(
    f"{EMPRESA} | Fuente actual: {st.session_state['nombre_archivo']}"
)


# =========================================================
# 9. DASHBOARD GERENCIAL
# =========================================================
if pagina == "Dashboard Gerencial":
    st.subheader("Dashboard gerencial")

    valor_total = df["valor_inventario"].sum()
    productos_reponer = (df["estado_stock"] == "Reponer").sum()
    unidades_stock = df["stock_actual"].sum()
    demanda_total = df["demanda_prom"].sum()

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Productos registrados",
        f"{len(df)}"
    )
    c2.metric(
        "Valor del inventario",
        formato_dinero(valor_total)
    )
    c3.metric(
        "Productos por reponer",
        f"{productos_reponer}"
    )
    c4.metric(
        "Demanda mensual promedio",
        f"{demanda_total:,.1f} unidades"
    )

    st.divider()

    # Gráfico 1: valor anual por producto
    col1, col2 = st.columns(2)

    with col1:
        fig_valor = px.bar(
            df.sort_values("valor_anual", ascending=True),
            x="valor_anual",
            y="producto",
            orientation="h",
            color="familia",
            title="Valor anual estimado por producto",
            labels={
                "valor_anual": "Valor anual (S/)",
                "producto": "Producto",
                "familia": "Línea de producto"
            },
            text_auto=".2s"
        )
        fig_valor.update_layout(
            legend_title_text="Línea",
            xaxis_tickformat=",.0f"
        )
        st.plotly_chart(fig_valor, use_container_width=True)

    # Gráfico 2: stock actual frente al ROP
    with col2:
        comparacion = df.melt(
            id_vars=["producto"],
            value_vars=["stock_actual", "ROP"],
            var_name="indicador",
            value_name="unidades"
        )

        comparacion["indicador"] = comparacion["indicador"].replace({
            "stock_actual": "Stock actual",
            "ROP": "Punto de reposición"
        })

        fig_stock = px.bar(
            comparacion,
            x="producto",
            y="unidades",
            color="indicador",
            barmode="group",
            title="Stock actual frente al punto de reposición",
            labels={
                "producto": "Producto",
                "unidades": "Unidades",
                "indicador": "Indicador"
            },
            text_auto=True
        )
        st.plotly_chart(fig_stock, use_container_width=True)

    # Gráfico 3: demanda mensual lineal
    st.subheader("📈 Tendencia de la demanda")

    demanda_larga = df.melt(
        id_vars=["producto"],
        value_vars=[
            "demanda_mensual_jun",
            "demanda_mensual_jul",
            "demanda_mensual_ago"
        ],
        var_name="mes",
        value_name="demanda"
    )

    nombres_meses = {
        "demanda_mensual_jun": "Junio",
        "demanda_mensual_jul": "Julio",
        "demanda_mensual_ago": "Agosto"
    }

    demanda_larga["mes"] = demanda_larga["mes"].map(nombres_meses)

    fig_demanda = px.line(
        demanda_larga,
        x="mes",
        y="demanda",
        color="producto",
        markers=True,
        title="Evolución mensual de la demanda por producto",
        category_orders={
            "mes": ["Junio", "Julio", "Agosto"]
        },
        labels={
            "mes": "Mes",
            "demanda": "Unidades demandadas",
            "producto": "Producto"
        }
    )

    fig_demanda.update_traces(
        line=dict(width=3),
        marker=dict(size=9)
    )
    fig_demanda.update_layout(hovermode="x unified")
    st.plotly_chart(fig_demanda, use_container_width=True)

    st.divider()
    st.subheader("Alertas de inventario")

    alertas = df[df["estado_stock"] == "Reponer"]

    if alertas.empty:
        st.success("No hay productos por debajo de su punto de reposición.")
    else:
        st.warning(
            f"Hay {len(alertas)} producto(s) que requieren revisión."
        )
        st.dataframe(
            alertas[
                [
                    "producto",
                    "familia",
                    "stock_actual",
                    "SS",
                    "ROP",
                    "reponer_unidades",
                    "estado_stock"
                ]
            ],
            hide_index=True,
            use_container_width=True
        )


# =========================================================
# 10. CARGAR ARCHIVO EXCEL
# =========================================================
elif pagina == "Cargar Excel":
    st.subheader("📂 Importar base de datos desde Excel")

    st.write(
        "Carga tu archivo para actualizar los productos, las demandas "
        "mensuales, los precios, el stock y los tiempos de entrega."
    )

    st.info(
        "El archivo debe contener las columnas indicadas en la plantilla. "
        "Se recomienda utilizar el formato .xlsx."
    )

    plantilla = crear_excel(DATOS_DEMO)

    st.download_button(
        "⬇️ Descargar plantilla Excel",
        data=plantilla,
        file_name="plantilla_inventario_agricola.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    archivo = st.file_uploader(
        "Selecciona tu archivo Excel",
        type=["xlsx"]
    )

    if archivo is not None:
        try:
            libro = pd.ExcelFile(archivo)

            hoja = st.selectbox(
                "Selecciona la hoja de Excel",
                options=libro.sheet_names
            )

            datos_cargados = pd.read_excel(
                archivo,
                sheet_name=hoja
            )

            st.write("Vista previa del archivo:")
            st.dataframe(
                datos_cargados.head(10),
                use_container_width=True
            )

            if st.button("✅ Validar e importar datos", type="primary"):
                datos_validados = validar_datos(datos_cargados)

                st.session_state["datos_inventario"] = datos_validados
                st.session_state["nombre_archivo"] = archivo.name

                st.success(
                    "Archivo importado correctamente. "
                    "Los indicadores se actualizarán con los nuevos datos."
                )
                st.rerun()

        except Exception as e:
            st.error(f"No se pudo importar el archivo: {e}")

    st.divider()

    if st.button("Restaurar datos demostrativos"):
        st.session_state["datos_inventario"] = DATOS_DEMO.copy()
        st.session_state["nombre_archivo"] = "Datos demostrativos"
        st.success("Se restauraron los datos de ejemplo.")
        st.rerun()


# =========================================================
# 11. BASE DE DATOS
# =========================================================
elif pagina == "Base de Datos":
    st.subheader("📋 Base de datos de productos")

    st.write(
        "Esta tabla muestra los datos originales junto con los indicadores calculados."
    )

    columnas_mostrar = [
        "producto",
        "familia",
        "precio_unit",
        "stock_actual",
        "demanda_mensual_jun",
        "demanda_mensual_jul",
        "demanda_mensual_ago",
        "lead_time_dias",
        "sigma_lt",
        "demanda_prom",
        "valor_anual",
        "clase",
        "SS",
        "ROP",
        "estado_stock"
    ]

    st.dataframe(
        df[columnas_mostrar],
        hide_index=True,
        use_container_width=True
    )

    st.caption(
        "Los datos demostrativos son ficticios. Sustitúyelos por información real "
        "antes de utilizar los resultados para tomar decisiones."
    )


# =========================================================
# 12. INDICADORES DE DEMANDA
# =========================================================
elif pagina == "Indicadores de Demanda":
    st.subheader("📈 Indicadores y comportamiento de la demanda")

    st.write(
        "Compara la demanda de junio, julio y agosto para identificar "
        "tendencias, cambios y productos con mayor movimiento."
    )

    # Selección de productos
    productos_seleccionados = st.multiselect(
        "Selecciona los productos que deseas analizar",
        options=df["producto"].tolist(),
        default=df["producto"].tolist()
    )

    if not productos_seleccionados:
        st.info("Selecciona al menos un producto para visualizar los gráficos.")
    else:
        df_filtrado = df[
            df["producto"].isin(productos_seleccionados)
        ].copy()

        # Preparar datos para los gráficos
        datos_lineales = df_filtrado.melt(
            id_vars=["producto", "familia"],
            value_vars=[
                "demanda_mensual_jun",
                "demanda_mensual_jul",
                "demanda_mensual_ago"
            ],
            var_name="mes",
            value_name="unidades"
        )

        orden_meses = {
            "demanda_mensual_jun": "Junio",
            "demanda_mensual_jul": "Julio",
            "demanda_mensual_ago": "Agosto"
        }

        datos_lineales["mes"] = datos_lineales["mes"].map(orden_meses)

        # Indicadores principales
        demanda_promedio = df_filtrado["demanda_prom"].mean()
        mayor_demanda = df_filtrado["demanda_prom"].max()
        demanda_acumulada = df_filtrado[
            [
                "demanda_mensual_jun",
                "demanda_mensual_jul",
                "demanda_mensual_ago"
            ]
        ].to_numpy().sum()

        k1, k2, k3 = st.columns(3)

        k1.metric(
            "Demanda mensual promedio por producto",
            f"{demanda_promedio:,.1f}"
        )
        k2.metric(
            "Mayor promedio mensual",
            f"{mayor_demanda:,.1f}"
        )
        k3.metric(
            "Demanda acumulada de 3 meses",
            f"{demanda_acumulada:,.0f}"
        )

        st.divider()

        # Gráfico lineal por producto
        fig_lineal = px.line(
            datos_lineales,
            x="mes",
            y="unidades",
            color="producto",
            markers=True,
            category_orders={
                "mes": ["Junio", "Julio", "Agosto"]
            },
            title="Gráfico lineal: evolución de la demanda",
            labels={
                "mes": "Mes",
                "unidades": "Demanda (unidades)",
                "producto": "Producto"
            }
        )

        fig_lineal.update_traces(
            line=dict(width=3),
            marker=dict(size=9)
        )
        fig_lineal.update_layout(
            hovermode="x unified",
            legend_title_text="Producto"
        )

        st.plotly_chart(
            fig_lineal,
            use_container_width=True
        )

        # Gráfico de barras por mes
        fig_barras = px.bar(
            datos_lineales,
            x="mes",
            y="unidades",
            color="producto",
            barmode="group",
            category_orders={
                "mes": ["Junio", "Julio", "Agosto"]
            },
            title="Comparación mensual de la demanda",
            labels={
                "mes": "Mes",
                "unidades": "Demanda (unidades)",
                "producto": "Producto"
            },
            text_auto=True
        )

        st.plotly_chart(
            fig_barras,
            use_container_width=True
        )

        # Tabla resumen de demanda
        st.subheader("Resumen de indicadores por producto")

        resumen = df_filtrado[
            [
                "producto",
                "familia",
                "demanda_mensual_jun",
                "demanda_mensual_jul",
                "demanda_mensual_ago",
                "demanda_prom",
                "sigma_mensual"
            ]
        ].copy()

        resumen = resumen.rename(columns={
            "producto": "Producto",
            "familia": "Línea",
            "demanda_mensual_jun": "Demanda junio",
            "demanda_mensual_jul": "Demanda julio",
            "demanda_mensual_ago": "Demanda agosto",
            "demanda_prom": "Promedio mensual",
            "sigma_mensual": "Desviación estándar"
        })

        st.dataframe(
            resumen,
            hide_index=True,
            use_container_width=True
        )

        st.caption(
            "Importante: solo hay tres meses de historial en esta versión. "
            "Los gráficos muestran el comportamiento observado y no constituyen "
            "un pronóstico estadístico de la demanda futura."
        )


# =========================================================
# 13. ANÁLISIS ABC
# =========================================================
elif pagina == "Análisis ABC":
    st.subheader("📊 Análisis ABC de productos")

    st.write(
        "La clasificación ABC prioriza los productos según su valor anual estimado."
    )

    total_valor = df["valor_anual"].sum()

    a, b, c = st.columns(3)

    a.metric(
        "Valor anual estimado",
        formato_dinero(total_valor)
    )
    b.metric(
        "Productos clase A",
        int((df["clase"] == "A").sum())
    )
    c.metric(
        "Productos clase B o C",
        int(df["clase"].isin(["B", "C"]).sum())
    )

    # Pareto
    pareto = df.sort_values(
        "valor_anual",
        ascending=False
    ).reset_index(drop=True)

    pareto["porcentaje_acumulado"] = pareto["pct_acum"] * 100

    fig_pareto = go.Figure()

    fig_pareto.add_trace(
        go.Bar(
            x=pareto["producto"],
            y=pareto["valor_anual"],
            name="Valor anual (S/)",
            yaxis="y",
            text=[
                f"S/ {v:,.0f}" for v in pareto["valor_anual"]
            ],
            textposition="auto"
        )
    )

    fig_pareto.add_trace(
        go.Scatter(
            x=pareto["producto"],
            y=pareto["porcentaje_acumulado"],
            name="% acumulado",
            yaxis="y2",
            mode="lines+markers+text",
            text=[
                f"{v:.1f}%"
                for v in pareto["porcentaje_acumulado"]
            ],
            textposition="top center",
            line=dict(width=3)
        )
    )

    fig_pareto.update_layout(
        title="Diagrama de Pareto para la clasificación ABC",
        xaxis_title="Producto",
        yaxis=dict(
            title="Valor anual (S/)",
            tickformat=",.0f"
        ),
        yaxis2=dict(
            title="Porcentaje acumulado",
            overlaying="y",
            side="right",
            range=[0, 110],
            ticksuffix="%"
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0
        ),
        hovermode="x unified"
    )

    st.plotly_chart(
        fig_pareto,
        use_container_width=True
    )

    st.subheader("Detalle de clasificación")

    st.dataframe(
        df[
            [
                "producto",
                "familia",
                "valor_anual",
                "pct_valor",
                "pct_acum",
                "clase"
            ]
        ].style.format({
            "valor_anual": "S/ {:,.2f}",
            "pct_valor": "{:.1%}",
            "pct_acum": "{:.1%}"
        }),
        hide_index=True,
        use_container_width=True
    )

    st.caption(
        "Los umbrales de referencia son 80% y 95% del valor acumulado. "
        "La categoría puede superar un umbral al incluir el producto que lo cruza."
    )


# =========================================================
# 14. STOCK DE SEGURIDAD Y PUNTO DE REPOSICIÓN
# =========================================================
elif pagina == "Stock de Seguridad y ROP":
    st.subheader("📦 Stock de seguridad y punto de reposición")

    z = {
        90: 1.282,
        95: 1.645,
        97.5: 1.960,
        99: 2.326
    }[nivel_servicio]

    st.write(f"Nivel de servicio seleccionado: **{nivel_servicio}%**")
    st.write(f"Factor Z utilizado: **{z}**")

    st.latex(r"SS=Z\sqrt{L\sigma_d^2+\bar d^2\sigma_{LT}^2}")
    st.latex(r"ROP=\bar d L+SS")

    st.caption(
        "Donde SS es el stock de seguridad, ROP el punto de reposición, "
        "L el tiempo de entrega, σd la variabilidad diaria estimada, "
        "d̄ la demanda diaria promedio y σLT la desviación del tiempo de entrega."
    )

    col1, col2 = st.columns(2)

    with col1:
        fig_ss = px.bar(
            df.sort_values("SS", ascending=False),
            x="producto",
            y="SS",
            color="familia",
            title="Stock de seguridad por producto",
            labels={
                "producto": "Producto",
                "SS": "Stock de seguridad (unidades)",
                "familia": "Línea"
            },
            text_auto=True
        )
        st.plotly_chart(fig_ss, use_container_width=True)

    with col2:
        fig_rop = go.Figure()

        fig_rop.add_trace(
            go.Bar(
                x=df["producto"],
                y=df["stock_actual"],
                name="Stock actual"
            )
        )

        fig_rop.add_trace(
            go.Scatter(
                x=df["producto"],
                y=df["ROP"],
                name="Punto de reposición",
                mode="lines+markers",
                line=dict(width=3)
            )
        )

        fig_rop.update_layout(
            title="Stock actual frente al punto de reposición",
            xaxis_title="Producto",
            yaxis_title="Unidades",
            hovermode="x unified"
        )

        st.plotly_chart(fig_rop, use_container_width=True)

    st.subheader("Tabla de reposición")

    st.dataframe(
        df[
            [
                "producto",
                "stock_actual",
                "demanda_diaria",
                "lead_time_dias",
                "SS",
                "ROP",
                "estado_stock",
                "reponer_unidades"
            ]
        ].style.format({
            "demanda_diaria": "{:.2f}"
        }),
        hide_index=True,
        use_container_width=True
    )

    st.caption(
        "La cantidad sugerida es una referencia mínima para alcanzar el ROP. "
        "No considera pedidos en tránsito, órdenes pendientes ni restricciones "
        "de compra; incorpora esos datos antes de emitir una orden real."
    )


# =========================================================
# 15. REPORTE FINAL
# =========================================================
elif pagina == "Reporte Final":
    st.subheader("📑 Reporte de gestión de inventarios")

    productos_reponer = df[df["estado_stock"] == "Reponer"]

    st.markdown(f"**Empresa:** {EMPRESA}")
    st.markdown(f"**Nivel de servicio:** {nivel_servicio}%")
    st.markdown(f"**Fuente de datos:** {st.session_state['nombre_archivo']}")

    st.divider()

    r1, r2, r3 = st.columns(3)

    r1.metric(
        "Productos analizados",
        len(df)
    )
    r2.metric(
        "Productos que requieren reposición",
        len(productos_reponer)
    )
    r3.metric(
        "Valor actual del inventario",
        formato_dinero(df["valor_inventario"].sum())
    )

    st.subheader("Recomendaciones")

    if productos_reponer.empty:
        st.success(
            "Ningún producto está en o por debajo de su punto de reposición. "
            "Continúa monitoreando los niveles de stock."
        )
    else:
        st.warning(
            "Revisa los productos que están en o por debajo del punto de reposición."
        )

        st.dataframe(
            productos_reponer[
                [
                    "producto",
                    "familia",
                    "stock_actual",
                    "ROP",
                    "reponer_unidades"
                ]
            ],
            hide_index=True,
            use_container_width=True
        )

    st.subheader("Exportar resultados")

    archivo_excel = crear_excel(df)

    st.download_button(
        "⬇️ Descargar reporte completo en Excel",
        data=archivo_excel,
        file_name="reporte_inventarios_agricola_progreso.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    archivo_csv = df.to_csv(
        index=False
    ).encode("utf-8-sig")

    st.download_button(
        "⬇️ Descargar reporte en CSV",
        data=archivo_csv,
        file_name="reporte_inventarios_agricola_progreso.csv",
        mime="text/csv"
    )

    st.caption(
        "El sistema es una herramienta de apoyo académico y operativo. "
        "Verifica las unidades, los datos de demanda y los tiempos de entrega "
        "con la información real de la empresa."
    )


# =========================================================
# 16. PIE DE PÁGINA
# =========================================================
st.divider()

st.caption(
    f"{EMPRESA} | Sistema de Gestión y Control de Inventarios"
)
