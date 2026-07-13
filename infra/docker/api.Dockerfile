FROM golang:1.24-alpine AS build

WORKDIR /src/apps/api
COPY go.mod go.sum ./
RUN go mod download
COPY . ./
RUN CGO_ENABLED=0 go build -trimpath -o /out/mirofish-api ./cmd/api

FROM alpine:3.22
RUN apk add --no-cache ca-certificates wget
COPY --from=build /out/mirofish-api /usr/local/bin/mirofish-api
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/mirofish-api"]
