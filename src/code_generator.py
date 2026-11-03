import random
from datetime import datetime


class CodeGenerator:
    """Genera bloques de código React + TypeScript realistas y extensos para que las
    capturas de pantalla del monitor de actividad muestren trabajo real en el editor."""

    def __init__(self):
        self.nombres_componentes = [
            "Dashboard", "UserProfile", "OrderList", "InvoiceView",
            "SettingsPanel", "ActivityFeed", "ProductCard", "SearchBar",
            "NotificationsMenu", "BillingForm", "AnalyticsChart", "CustomerTable",
            "ReportsView", "AuditLog", "TeamMembers",
        ]
        self.nombres_interfaces = [
            "Dashboard", "UserList", "OrderTable", "InvoiceForm", "AnalyticsPanel",
            "SettingsForm", "ActivityLog", "ProductGrid", "SearchBox", "BillingPage",
        ]
        self.nombres_tipos = [
            "User", "Order", "Product", "Invoice", "Session", "Activity",
            "Report", "Customer", "Transaction", "Metrics",
        ]
        self.nombres_funciones = [
            "fetchUserById", "fetchOrders", "submitInvoice", "updateProfile",
            "loadActivities", "exportReport", "validateEmail", "calculateTotals",
            "parseResponse", "buildQueryParams", "filterByStatus", "syncData",
            "createTransaction", "getMetrics", "getAuditLog",
        ]
        self.rutas_archivos = [
            "src/components/Dashboard.tsx",
            "src/components/UserProfile.tsx",
            "src/components/OrderList.tsx",
            "src/components/InvoiceView.tsx",
            "src/components/SettingsPanel.tsx",
            "src/components/ActivityFeed.tsx",
            "src/components/ProductCard.tsx",
            "src/components/AnalyticsChart.tsx",
            "src/pages/dashboard/index.tsx",
            "src/features/billing/InvoiceView.tsx",
            "src/features/reports/ReportsView.tsx",
            "src/views/admin/CustomerTable.tsx",
            "src/views/admin/TeamMembers.tsx",
            "src/screens/SettingsPanel.tsx",
            "src/hooks/useDashboardData.ts",
        ]
        self.imports_fijos = [
            "import React, { useState, useEffect, useCallback, useMemo } from 'react';",
            "import type { FC } from 'react';",
            "import { api } from '../../services/api';",
            "import { DataTable, EmptyState, SearchBar, Spinner } from '../../components';",
        ]
        self.imports_variables = [
            "import { useNavigate, useParams, Link } from 'react-router-dom';",
            "import { formatDate, formatCurrency, formatNumber } from '../../utils/formatters';",
            "import { useTheme, useAuth } from '../../hooks';",
            "import type { ApiResponse, FilterOption, SortOrder } from '../../types';",
            "import { toast } from 'react-hot-toast';",
        ]
        self.comentarios = [
            "// Cargar los datos iniciales del módulo",
            "// Validar la información antes de enviarla al servidor",
            "// Manejar el error de red de forma controlada",
            "// Normalizar la entrada proporcionada por el usuario",
            "// Construir los parámetros de la consulta",
            "// Registrar el evento en el log de auditoría",
            "// Filtrar los elementos según el estado seleccionado",
            "// Calcular el total acumulado de la lista",
            "// Actualizar el estado local con la respuesta",
            "// Verificar permisos antes de ejecutar la acción",
        ]
        self.docstrings = [
            "Módulo de panel de administración principal.",
            "Vista de gestión de usuarios y permisos.",
            "Componente de listado y filtrado de pedidos.",
            "Módulo de facturación y generación de reportes.",
            "Panel de métricas y analítica de uso.",
            "Formulario de configuración del perfil.",
            "Registro de actividad y auditoría del sistema.",
            "Catálogo de productos con búsqueda y paginación.",
            "Gestión de notificaciones y alertas del equipo.",
            "Visualización y seguimiento de órdenes de compra.",
        ]
        self.excepciones = [
            "Error", "TypeError", "SyntaxError", "NetworkError", "RangeError",
        ]

    def generar_codigo(self, min_lineas: int = 45, max_lineas: int = 110) -> str:
        """Genera un bloque de código React/TypeScript realista con al menos `min_lineas` líneas."""
        if (type(min_lineas) is not int or type(max_lineas) is not int
                or not 0 < min_lineas <= max_lineas):
            raise ValueError("El rango de líneas debe contener enteros positivos en orden")
        self._usados = set()
        self._export_default_usado = False
        self._constantes_usadas = False
        bloques = [self._generar_modulo()]
        total = len(bloques[0])
        while total < min_lineas:
            bloque = self._generar_bloque_extra()
            bloques.append(bloque)
            total += len(bloque)
        lineas = self._truncar_por_bloques(bloques, min_lineas, max_lineas)
        return "\n".join(lineas).rstrip()

    def obtener_codigo(self) -> str:
        """Alias de generar_codigo para una interfaz común entre fuentes de código."""
        return self.generar_codigo()

    def _truncar_por_bloques(self, bloques: list, min_lineas: int, max_lineas: int) -> list:
        """Recorta por bloques completos para no dejar código a mitad con llaves desbalanceadas."""
        resultado = []
        total = 0
        for bloque in bloques:
            if total + len(bloque) > max_lineas and total >= min_lineas:
                break
            resultado.extend(bloque)
            total += len(bloque)
        return resultado

    def _nombre_unico(self, lista: list) -> str:
        """Devuelve un nombre de la lista que no se haya usado ya en este archivo."""
        disponibles = [nombre for nombre in lista if nombre not in self._usados]
        nombre = random.choice(disponibles or lista)
        if not disponibles:
            sufijo = 2
            while f'{nombre}{sufijo}' in self._usados:
                sufijo += 1
            nombre = f'{nombre}{sufijo}'
        self._usados.add(nombre)
        return nombre

    def _generar_modulo(self) -> list:
        lineas = []
        lineas.append("// " + random.choice(self.rutas_archivos))
        lineas.append("")
        lineas.append("/**")
        lineas.append(" * " + random.choice(self.docstrings))
        lineas.append(" * ")
        lineas.append(" * Última modificación: " + datetime.now().strftime("%d/%m/%Y %H:%M"))
        lineas.append(" */")
        lineas.append("")
        lineas.extend(self.imports_fijos)
        lineas.extend(random.sample(self.imports_variables, k=random.randint(1, 3)))
        lineas.append("")
        return lineas

    def _generar_constantes(self) -> list:
        if self._constantes_usadas:
            return []
        self._constantes_usadas = True
        lineas = []
        lineas.append(f"export const DEFAULT_PAGE_SIZE = {random.randint(10, 50)};")
        lineas.append("export const API_BASE_URL = process.env.REACT_APP_API_URL ?? '/api/v1';")
        lineas.append(f"export const APP_NAME = '{random.choice(self.nombres_interfaces)}App';")
        lineas.append("")
        return lineas

    def _generar_interface(self, tipo: str) -> tuple:
        nombre = self._nombre_unico(self.nombres_interfaces)
        lineas = []
        lineas.append(f"export interface {nombre}Props {{")
        lineas.append(f"  items: {tipo}[];")
        lineas.append("  onSelect: (id: string) => void;")
        lineas.append("}")
        lineas.append("")
        lineas.append(f"export type {tipo} = {{")
        lineas.append("  id: string;")
        lineas.append("  name: string;")
        lineas.append("  email: string;")
        lineas.append("  role: 'admin' | 'user';")
        lineas.append("  active: boolean;")
        lineas.append("  createdAt: string;")
        lineas.append("};")
        return lineas, nombre

    def _generar_funcion(self, tipo: str, nombre_funcion: str) -> list:
        lineas = []
        lineas.append(f"const {nombre_funcion} = async (filtro: string): Promise<{tipo}[]> => {{")
        lineas.append("  try {")
        lineas.append(f"    const response = await api.get<{tipo}[]>(`/api/v1/{nombre_funcion}?q=${{filtro}}`);")
        lineas.append("    if (!response.data) {")
        lineas.append("      throw new Error('Respuesta vacía del servidor');")
        lineas.append("    }")
        lineas.append("    return response.data;")
        lineas.append("  } catch (error) {")
        lineas.append(f"    console.error('Error en {nombre_funcion}:', error);")
        lineas.append("    throw error;")
        lineas.append("  }")
        lineas.append("};")
        return lineas

    def _generar_componente(self, tipo: str, nombre_interface: str, nombre_funcion: str) -> list:
        nombre = self._nombre_unico(self.nombres_componentes)
        lineas = []
        lineas.append(f"export const {nombre}: FC<{nombre_interface}Props> = ({{ items, onSelect }}) => {{")
        lineas.append("  const [isLoading, setIsLoading] = useState(false);")
        lineas.append("  const [searchTerm, setSearchTerm] = useState('');")
        lineas.append(f"  const [data, setData] = useState<{tipo}[]>([]);")
        lineas.append("  const [currentPage, setCurrentPage] = useState(1);")
        lineas.append("")
        lineas.append("  useEffect(() => {")
        lineas.append(f"    {random.choice(self.comentarios)}")
        lineas.append("    setIsLoading(true);")
        lineas.append(f"    {nombre_funcion}(searchTerm)")
        lineas.append("      .then((response) => setData(response))")
        lineas.append("      .catch((err) => console.error('Error al cargar los datos:', err))")
        lineas.append("      .finally(() => setIsLoading(false));")
        lineas.append("  }, [searchTerm]);")
        lineas.append("")
        lineas.append("  const filteredItems = useMemo(() => {")
        lineas.append("    return items.filter((item) =>")
        lineas.append("      item.name.toLowerCase().includes(searchTerm.toLowerCase())")
        lineas.append("    );")
        lineas.append("  }, [items, searchTerm]);")
        lineas.append("")
        lineas.append("  const handleSelect = useCallback((id: string) => {")
        lineas.append("    setCurrentPage(parseInt(id, 10));")
        lineas.append("    onSelect(id);")
        lineas.append("  }, [onSelect]);")
        lineas.append("")
        lineas.append("  if (isLoading) {")
        lineas.append("    return <Spinner size='lg' label='Cargando datos' />;")
        lineas.append("  }")
        lineas.append("")
        lineas.append("  return (")
        lineas.append('    <div className="container">')
        lineas.append('      <header className="header">')
        lineas.append('        <h1 className="title">Panel de administración</h1>')
        lineas.append('        <p className="summary">{data.length} registros cargados</p>')
        lineas.append("        <SearchBar value={searchTerm} onChange={setSearchTerm} />")
        lineas.append("      </header>")
        lineas.append("      {filteredItems.length > 0 ? (")
        lineas.append("        <DataTable")
        lineas.append("          data={filteredItems}")
        lineas.append("          onSelect={handleSelect}")
        lineas.append("          currentPage={currentPage}")
        lineas.append("        />")
        lineas.append("      ) : (")
        lineas.append("        <EmptyState message='No se encontraron resultados' />")
        lineas.append("      )}")
        lineas.append("    </div>")
        lineas.append("  );")
        lineas.append("};")
        lineas.append("")
        if not self._export_default_usado:
            lineas.append(f"export default {nombre};")
            self._export_default_usado = True
        return lineas

    def _generar_bloque_extra(self) -> list:
        lineas = []
        tipo = self._nombre_unico(self.nombres_tipos)
        if random.random() < 0.25:
            lineas += self._generar_constantes()
        lineas_interface, nombre_interface = self._generar_interface(tipo)
        lineas += lineas_interface
        lineas.append("")
        nombre_funcion = self._nombre_unico(self.nombres_funciones)
        lineas += self._generar_funcion(tipo, nombre_funcion)
        lineas.append("")
        lineas += self._generar_componente(tipo, nombre_interface, nombre_funcion)
        lineas.append("")
        return lineas
