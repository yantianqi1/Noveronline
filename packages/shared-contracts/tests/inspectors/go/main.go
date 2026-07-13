package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strconv"
)

type inspection struct {
	Constants       map[string]string `json:"constants"`
	StarterPayload  []string          `json:"starter_payload"`
	WriterEventJSON []string          `json:"writer_event_json"`
}

func main() {
	if len(os.Args) != 2 {
		panic("repository root argument is required")
	}
	path := filepath.Join(os.Args[1], "apps/api/internal/workflows/writer.go")
	file, err := parser.ParseFile(token.NewFileSet(), path, nil, parser.SkipObjectResolution)
	if err != nil {
		panic(err)
	}
	result := inspection{
		Constants:       stringConstants(file),
		StarterPayload:  starterPayloadKeys(file),
		WriterEventJSON: structJSONFields(file, "WriterEvent"),
	}
	if err := json.NewEncoder(os.Stdout).Encode(result); err != nil {
		panic(err)
	}
}

func stringConstants(file *ast.File) map[string]string {
	values := map[string]string{}
	for _, declaration := range file.Decls {
		generic, ok := declaration.(*ast.GenDecl)
		if !ok || generic.Tok != token.CONST {
			continue
		}
		for _, item := range generic.Specs {
			spec, ok := item.(*ast.ValueSpec)
			if !ok || len(spec.Names) != 1 || len(spec.Values) != 1 {
				continue
			}
			literal, ok := spec.Values[0].(*ast.BasicLit)
			if !ok || literal.Kind != token.STRING {
				continue
			}
			value, err := strconv.Unquote(literal.Value)
			if err == nil {
				values[spec.Names[0].Name] = value
			}
		}
	}
	return values
}

func starterPayloadKeys(file *ast.File) []string {
	for _, declaration := range file.Decls {
		function, ok := declaration.(*ast.FuncDecl)
		if !ok || function.Name.Name != "StartWriterRun" || function.Recv == nil || function.Body == nil {
			continue
		}
		var keys []string
		ast.Inspect(function.Body, func(node ast.Node) bool {
			assignment, ok := node.(*ast.AssignStmt)
			if !ok || len(assignment.Lhs) != 1 || len(assignment.Rhs) != 1 {
				return true
			}
			identifier, ok := assignment.Lhs[0].(*ast.Ident)
			if !ok || identifier.Name != "payload" {
				return true
			}
			literal, ok := assignment.Rhs[0].(*ast.CompositeLit)
			if !ok {
				return true
			}
			for _, element := range literal.Elts {
				pair, ok := element.(*ast.KeyValueExpr)
				if !ok {
					continue
				}
				key, ok := pair.Key.(*ast.BasicLit)
				if !ok || key.Kind != token.STRING {
					continue
				}
				if value, err := strconv.Unquote(key.Value); err == nil {
					keys = append(keys, value)
				}
			}
			return false
		})
		if len(keys) > 0 {
			sort.Strings(keys)
			return keys
		}
	}
	panic("TemporalWriterStarter.StartWriterRun payload map was not found")
}

func structJSONFields(file *ast.File, typeName string) []string {
	for _, declaration := range file.Decls {
		generic, ok := declaration.(*ast.GenDecl)
		if !ok || generic.Tok != token.TYPE {
			continue
		}
		for _, item := range generic.Specs {
			spec, ok := item.(*ast.TypeSpec)
			if !ok || spec.Name.Name != typeName {
				continue
			}
			structure, ok := spec.Type.(*ast.StructType)
			if !ok {
				panic(fmt.Sprintf("%s is no longer a struct", typeName))
			}
			fields := make([]string, 0, len(structure.Fields.List))
			for _, field := range structure.Fields.List {
				if field.Tag == nil {
					continue
				}
				tag, err := strconv.Unquote(field.Tag.Value)
				if err != nil {
					continue
				}
				if name := reflect.StructTag(tag).Get("json"); name != "" {
					if comma := indexByte(name, ','); comma >= 0 {
						name = name[:comma]
					}
					fields = append(fields, name)
				}
			}
			sort.Strings(fields)
			return fields
		}
	}
	panic(fmt.Sprintf("struct %s was not found", typeName))
}

func indexByte(value string, target byte) int {
	for index := range value {
		if value[index] == target {
			return index
		}
	}
	return -1
}
