{{- define "synchro-iobeya-github.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "synchro-iobeya-github.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s" $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "synchro-iobeya-github.labels" -}}
app.kubernetes.io/name: {{ include "synchro-iobeya-github.name" . }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "synchro-iobeya-github.selectorLabels" -}}
app.kubernetes.io/name: {{ include "synchro-iobeya-github.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
