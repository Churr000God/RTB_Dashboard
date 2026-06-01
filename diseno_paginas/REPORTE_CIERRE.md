# Diseno de pagina - Reporte de cierre RTB

Superficie: HTML estatico generado por `rtb_html.py`.

Registro de diseno: producto operativo. Lo usa direccion/finanzas/operaciones para decidir que corregir en ventas, almacen, compras, inventario, gastos y flujo.

## Escena de uso

Una persona de direccion revisa el cierre mensual en laptop durante la manana, comparte pantalla con finanzas y operaciones, y necesita detectar en minutos que movera caja, inventario y cobranza el siguiente mes.

## Problemas del reporte actual

- Exceso de secciones largas sin navegacion persistente.
- Muchas tablas tienen igual peso visual aunque algunas son soporte y otras son decision.
- Alertas criticas aparecen tarde, despues de todos los modulos.
- El color actual mezcla fondo claro en hero con secciones oscuras; la jerarquia se siente partida.
- Hay emojis como iconos de modulo; para producto operativo conviene usar iconos consistentes o texto sobrio.
- Tablas anchas usan `table-layout: fixed`, pero falta tratamiento dedicado para mobile.
- El reporte explica terminos, pero no separa claramente "decision", "evidencia" y "detalle".
- Algunas metricas necesitan etiqueta de base temporal: creado en mes, entregado en mes, facturado en mes, cobrado en mes.

## Direccion de redisenio

Crear un dashboard narrativo y operativo:

- Primera pantalla: resumen de salud del mes, riesgos y acciones.
- Navegacion por modulos con anclas: Ventas, Operacion, Compras, Inventario, OPEX, P&L, Hallazgos.
- Cada modulo debe tener: decision principal, 3-5 KPIs, visual principal, tabla de evidencia, notas de calidad de dato.
- Las alertas deben aparecer cerca del dato que las origina y tambien consolidarse arriba.
- Mantener glosario, pero como soporte plegable o bloque final compacto.

## Estructura recomendada

1. Header compacto: RTB, periodo, fecha de exportacion, fecha de generacion.
2. Executive Command Center:
   - Caja: flujo neto, utilidad ajustada, CxC, CxP, inventario inmovilizado.
   - Lista de 5 alertas priorizadas con responsable sugerido.
   - Diferenciar "resultado financiero", "riesgo operativo", "calidad de datos".
3. Modulo Ventas:
   - Conversion qty/monto, aprobado, expirado, ticket, Ariba.
   - Grafica: cotizado vs aprobado por semana.
   - Tabla: estados y top clientes.
   - Alerta: tipo de pago sin definir.
4. Modulo Operacion:
   - Pedidos creados, entregados, sin factura, facturados sin entregar.
   - Grafica: preparacion/entrega/ciclo.
   - Tabla: pedidos en riesgo.
5. Modulo Compras:
   - Total compras, pagado/no pagado, CxP, concentracion proveedor.
   - Grafica: status pago y top proveedores.
   - Alerta: 99 por definir.
6. Modulo Inventario:
   - Stock total, inmovilizado, activo, salidas, entradas.
   - Grafica: evolucion stock vs inmovilizado.
   - Tabla: SKUs por valor y salidas.
7. Modulo OPEX:
   - OPEX total, recurrente, fiscal extraordinario, deducible, sin folio.
   - Grafica: categorias y semanas.
   - Tabla: carga fiscal detectada.
8. P&L y Flujo:
   - Separar caja real de P&L operativo.
   - Mostrar claramente que el P&L actual no es contabilidad formal devengada.
9. Hallazgos y recomendaciones:
   - Convertir recomendaciones en acciones con prioridad, modulo, impacto y fecha objetivo.
10. Glosario:
   - Mantener definiciones, sin interrumpir lectura ejecutiva.

## Lineamientos UI/UX

- Usar una paleta restringida: neutros tintados, un acento principal y colores semanticos para bueno, alerta y riesgo.
- Evitar gradientes decorativos, glassmorphism, tarjetas identicas en exceso y hero de metricas genericas.
- Usar tipografia de alta legibilidad y numeros tabulares para dinero/porcentajes.
- En mobile, las tablas deben ir en `overflow-x-auto` o transformarse en filas tipo registro cuando sean criticas.
- Cada grafica debe tener tabla alternativa o estar junto a la tabla fuente.
- No depender de color como unico indicador: usar etiqueta textual `OK`, `Atencion`, `Riesgo`, `Dato incompleto`.
- Mantener HTML offline. Si se cambia Chart.js, seguir embebiendo localmente.

## Graficas recomendadas

- Ventas: barras agrupadas cotizado/aprobado por semana.
- Conversion: barras horizontales por estado y por rol.
- Operacion: small multiples para preparacion, entrega y ciclo de facturacion.
- Compras: barras horizontales por proveedor y dona/status solo si hay tabla al lado.
- Inventario: linea historica total/inmovilizado y barra 100% activo vs inmovilizado.
- OPEX: barras por categoria, resaltando fiscal extraordinario.
- P&L: waterfall o tabla escalonada para explicar ingresos, compras, margen, OPEX y utilidad.

## Preguntas abiertas para el siguiente ciclo

1. Confirmar si el redisenio sera HTML estatico puro o si se migrara a una app interactiva.
   Recomendacion: mantener HTML estatico primero y extraer componentes/helpers antes de considerar framework.
2. Confirmar audiencia principal.
   Recomendacion: direccion y finanzas primero, operaciones como segunda capa de detalle.
3. Confirmar si mayo en snapshot historico debe aparecer dentro de un cierre de abril.
   Recomendacion: mostrarlo solo como "dato posterior disponible" o excluirlo del cierre formal.
