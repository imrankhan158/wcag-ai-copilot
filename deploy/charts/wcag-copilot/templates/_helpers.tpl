{{/*
Expand the name of the chart.
*/}}
{{- define "wcag.name" -}}
{{- default .Chart.Name .Values.nameOverride | truncate 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
*/}}
{{- define "wcag.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | truncate 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | truncate 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | truncate 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "wcag.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | truncate 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "wcag.labels" -}}
helm.sh/chart: {{ include "wcag.chart" . }}
app.kubernetes.io/name: {{ include "wcag.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
