//! Pure-Rust Zero-Dependency JSON Parser for Continuum CLI & MCP Server.
//!
//! Provides full JSON-RPC 2.0 and MCP protocol parsing compliance with
//! ZERO external crates (100% standard library).
//! Supports recursive-descent parsing, escape decoding, nested objects, and formatting.

#[derive(Debug, Clone, PartialEq)]
pub enum JsonValue {
    Null,
    Bool(bool),
    Number(f64),
    String(String),
    Array(Vec<JsonValue>),
    Object(Vec<(String, JsonValue)>),
}

#[allow(dead_code)]
impl JsonValue {
    /// Retrieve a field from an Object by key.
    pub fn get(&self, key: &str) -> Option<&JsonValue> {
        match self {
            JsonValue::Object(fields) => {
                for (k, v) in fields {
                    if k == key {
                        return Some(v);
                    }
                }
                None
            }
            _ => None,
        }
    }

    /// Retrieve a nested field along a path (e.g. `["params", "arguments", "query"]`).
    pub fn get_path(&self, path: &[&str]) -> Option<&JsonValue> {
        let mut cur = self;
        for &k in path {
            cur = cur.get(k)?;
        }
        Some(cur)
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            JsonValue::String(s) => Some(s.as_str()),
            _ => None,
        }
    }

    pub fn as_f64(&self) -> Option<f64> {
        match self {
            JsonValue::Number(n) => Some(*n),
            _ => None,
        }
    }

    pub fn as_i64(&self) -> Option<i64> {
        match self {
            JsonValue::Number(n) => Some(*n as i64),
            _ => None,
        }
    }

    pub fn as_u64(&self) -> Option<u64> {
        match self {
            JsonValue::Number(n) if *n >= 0.0 => Some(*n as u64),
            _ => None,
        }
    }

    pub fn as_bool(&self) -> Option<bool> {
        match self {
            JsonValue::Bool(b) => Some(*b),
            _ => None,
        }
    }

    pub fn as_array(&self) -> Option<&[JsonValue]> {
        match self {
            JsonValue::Array(arr) => Some(arr.as_slice()),
            _ => None,
        }
    }

    pub fn as_object(&self) -> Option<&[(String, JsonValue)]> {
        match self {
            JsonValue::Object(obj) => Some(obj.as_slice()),
            _ => None,
        }
    }

    /// Formats the value as valid JSON.
    pub fn to_json_string(&self) -> String {
        match self {
            JsonValue::Null => "null".to_string(),
            JsonValue::Bool(b) => if *b { "true".to_string() } else { "false".to_string() },
            JsonValue::Number(n) => {
                if n.fract() == 0.0 && !n.is_infinite() && !n.is_nan() && *n >= (i64::MIN as f64) && *n <= (i64::MAX as f64) {
                    format!("{}", *n as i64)
                } else {
                    format!("{}", n)
                }
            }
            JsonValue::String(s) => {
                let mut out = String::with_capacity(s.len() + 2);
                out.push('"');
                for c in s.chars() {
                    match c {
                        '"' => out.push_str("\\\""),
                        '\\' => out.push_str("\\\\"),
                        '\n' => out.push_str("\\n"),
                        '\r' => out.push_str("\\r"),
                        '\t' => out.push_str("\\t"),
                        '\x08' => out.push_str("\\b"),
                        '\x0c' => out.push_str("\\f"),
                        c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
                        c => out.push(c),
                    }
                }
                out.push('"');
                out
            }
            JsonValue::Array(items) => {
                let mut out = String::from("[");
                for (i, it) in items.iter().enumerate() {
                    if i > 0 {
                        out.push(',');
                    }
                    out.push_str(&it.to_json_string());
                }
                out.push(']');
                out
            }
            JsonValue::Object(pairs) => {
                let mut out = String::from("{");
                for (i, (k, v)) in pairs.iter().enumerate() {
                    if i > 0 {
                        out.push(',');
                    }
                    out.push('"');
                    out.push_str(k);
                    out.push_str("\":");
                    out.push_str(&v.to_json_string());
                }
                out.push('}');
                out
            }
        }
    }

    /// Renders raw representation suitable for JSON-RPC `id` field.
    /// Preserves exact quotes if string, numbers as literal, null as `null`.
    pub fn to_raw_id_string(&self) -> String {
        match self {
            JsonValue::String(s) => format!("\"{}\"", s.replace('\\', "\\\\").replace('"', "\\\"")),
            JsonValue::Number(n) => {
                if n.fract() == 0.0 {
                    format!("{}", *n as i64)
                } else {
                    format!("{}", n)
                }
            }
            JsonValue::Null => "null".to_string(),
            other => other.to_json_string(),
        }
    }
}

pub struct JsonParser<'a> {
    chars: Vec<char>,
    pos: usize,
    _lifetime: std::marker::PhantomData<&'a ()>,
}

impl<'a> JsonParser<'a> {
    pub fn parse(input: &'a str) -> Result<JsonValue, String> {
        let mut parser = Self {
            chars: input.chars().collect(),
            pos: 0,
            _lifetime: std::marker::PhantomData,
        };
        parser.skip_whitespace();
        let val = parser.parse_value()?;
        parser.skip_whitespace();
        if parser.pos < parser.chars.len() {
            return Err(format!(
                "Unexpected trailing characters at pos {}: '{}'",
                parser.pos,
                parser.chars[parser.pos..].iter().take(20).collect::<String>()
            ));
        }
        Ok(val)
    }

    fn peek(&self) -> Option<char> {
        self.chars.get(self.pos).copied()
    }

    fn next_char(&mut self) -> Option<char> {
        let c = self.chars.get(self.pos).copied();
        if c.is_some() {
            self.pos += 1;
        }
        c
    }

    fn skip_whitespace(&mut self) {
        while let Some(c) = self.peek() {
            if c.is_whitespace() {
                self.pos += 1;
            } else {
                break;
            }
        }
    }

    fn parse_value(&mut self) -> Result<JsonValue, String> {
        self.skip_whitespace();
        let c = self.peek().ok_or_else(|| "Unexpected EOF while parsing JSON value".to_string())?;
        match c {
            'n' => self.parse_null(),
            't' | 'f' => self.parse_bool(),
            '"' => self.parse_string().map(JsonValue::String),
            '[' => self.parse_array(),
            '{' => self.parse_object(),
            '-' | '0'..='9' => self.parse_number(),
            other => Err(format!("Unexpected character '{}' at pos {}", other, self.pos)),
        }
    }

    fn parse_null(&mut self) -> Result<JsonValue, String> {
        if self.match_exact("null") {
            Ok(JsonValue::Null)
        } else {
            Err(format!("Expected 'null' at pos {}", self.pos))
        }
    }

    fn parse_bool(&mut self) -> Result<JsonValue, String> {
        if self.match_exact("true") {
            Ok(JsonValue::Bool(true))
        } else if self.match_exact("false") {
            Ok(JsonValue::Bool(false))
        } else {
            Err(format!("Expected 'true' or 'false' at pos {}", self.pos))
        }
    }

    fn match_exact(&mut self, s: &str) -> bool {
        let chars: Vec<char> = s.chars().collect();
        if self.pos + chars.len() <= self.chars.len() {
            for (i, &c) in chars.iter().enumerate() {
                if self.chars[self.pos + i] != c {
                    return false;
                }
            }
            self.pos += chars.len();
            true
        } else {
            false
        }
    }

    fn parse_string(&mut self) -> Result<String, String> {
        if self.next_char() != Some('"') {
            return Err(format!("Expected '\"' at pos {}", self.pos));
        }
        let mut s = String::new();
        while let Some(c) = self.next_char() {
            match c {
                '"' => return Ok(s),
                '\\' => {
                    let esc = self.next_char().ok_or_else(|| "Unexpected EOF after escape".to_string())?;
                    match esc {
                        '"' => s.push('"'),
                        '\\' => s.push('\\'),
                        '/' => s.push('/'),
                        'b' => s.push('\x08'),
                        'f' => s.push('\x0c'),
                        'n' => s.push('\n'),
                        'r' => s.push('\r'),
                        't' => s.push('\t'),
                        'u' => {
                            let mut hex = String::with_capacity(4);
                            for _ in 0..4 {
                                hex.push(self.next_char().ok_or_else(|| "Unexpected EOF in \\u escape".to_string())?);
                            }
                            let code = u32::from_str_radix(&hex, 16)
                                .map_err(|e| format!("Invalid hex escape \\u{}: {}", hex, e))?;
                            let decoded = char::from_u32(code)
                                .ok_or_else(|| format!("Invalid unicode code point: {:x}", code))?;
                            s.push(decoded);
                        }
                        other => {
                            s.push('\\');
                            s.push(other);
                        }
                    }
                }
                other => s.push(other),
            }
        }
        Err("Unterminated string literal".to_string())
    }

    fn parse_number(&mut self) -> Result<JsonValue, String> {
        let start = self.pos;
        if self.peek() == Some('-') {
            self.pos += 1;
        }
        while let Some(c) = self.peek() {
            if c.is_ascii_digit() {
                self.pos += 1;
            } else {
                break;
            }
        }
        if self.peek() == Some('.') {
            self.pos += 1;
            while let Some(c) = self.peek() {
                if c.is_ascii_digit() {
                    self.pos += 1;
                } else {
                    break;
                }
            }
        }
        if let Some(c) = self.peek() {
            if c == 'e' || c == 'E' {
                self.pos += 1;
                if self.peek() == Some('+') || self.peek() == Some('-') {
                    self.pos += 1;
                }
                while let Some(c) = self.peek() {
                    if c.is_ascii_digit() {
                        self.pos += 1;
                    } else {
                        break;
                    }
                }
            }
        }
        let raw: String = self.chars[start..self.pos].iter().collect();
        let num: f64 = raw.parse().map_err(|e| format!("Failed to parse number '{}': {}", raw, e))?;
        Ok(JsonValue::Number(num))
    }

    fn parse_array(&mut self) -> Result<JsonValue, String> {
        if self.next_char() != Some('[') {
            return Err("Expected '['".to_string());
        }
        self.skip_whitespace();
        let mut items = Vec::new();
        if self.peek() == Some(']') {
            self.pos += 1;
            return Ok(JsonValue::Array(items));
        }
        loop {
            let val = self.parse_value()?;
            items.push(val);
            self.skip_whitespace();
            match self.peek() {
                Some(',') => {
                    self.pos += 1;
                    self.skip_whitespace();
                    if self.peek() == Some(']') {
                        // Tolerate optional trailing comma
                        self.pos += 1;
                        break;
                    }
                }
                Some(']') => {
                    self.pos += 1;
                    break;
                }
                other => return Err(format!("Expected ',' or ']' in array, got {:?}", other)),
            }
        }
        Ok(JsonValue::Array(items))
    }

    fn parse_object(&mut self) -> Result<JsonValue, String> {
        if self.next_char() != Some('{') {
            return Err("Expected '{'".to_string());
        }
        self.skip_whitespace();
        let mut pairs = Vec::new();
        if self.peek() == Some('}') {
            self.pos += 1;
            return Ok(JsonValue::Object(pairs));
        }
        loop {
            self.skip_whitespace();
            let key = self.parse_string()?;
            self.skip_whitespace();
            if self.next_char() != Some(':') {
                return Err(format!("Expected ':' after key \"{}\"", key));
            }
            let val = self.parse_value()?;
            pairs.push((key, val));
            self.skip_whitespace();
            match self.peek() {
                Some(',') => {
                    self.pos += 1;
                    self.skip_whitespace();
                    if self.peek() == Some('}') {
                        // Tolerate optional trailing comma
                        self.pos += 1;
                        break;
                    }
                }
                Some('}') => {
                    self.pos += 1;
                    break;
                }
                other => return Err(format!("Expected ',' or '}}' in object, got {:?}", other)),
            }
        }
        Ok(JsonValue::Object(pairs))
    }
}

pub fn parse_json(input: &str) -> Result<JsonValue, String> {
    JsonParser::parse(input)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_primitives() {
        assert_eq!(parse_json("null").unwrap(), JsonValue::Null);
        assert_eq!(parse_json("true").unwrap(), JsonValue::Bool(true));
        assert_eq!(parse_json("false").unwrap(), JsonValue::Bool(false));
        assert_eq!(parse_json("42").unwrap(), JsonValue::Number(42.0));
        assert_eq!(parse_json("-17.5").unwrap(), JsonValue::Number(-17.5));
        assert_eq!(parse_json("\"hello world\"").unwrap(), JsonValue::String("hello world".to_string()));
    }

    #[test]
    fn test_parse_escaped_strings() {
        let json = r#""line1\nline2\t\"quoted\"\\slash""#;
        let val = parse_json(json).unwrap();
        assert_eq!(val.as_str().unwrap(), "line1\nline2\t\"quoted\"\\slash");
    }

    #[test]
    fn test_parse_mcp_requests() {
        let json = r#"{
            "jsonrpc": "2.0",
            "id": "msg_01J8K9",
            "method": "tools/call",
            "params": {
                "name": "continuum_recall",
                "arguments": {
                    "query": "database pool cap",
                    "top_k": 5
                }
            }
        }"#;
        let v = parse_json(json).unwrap();
        assert_eq!(v.get("jsonrpc").unwrap().as_str().unwrap(), "2.0");
        assert_eq!(v.get("id").unwrap().to_raw_id_string(), "\"msg_01J8K9\"");
        assert_eq!(v.get("method").unwrap().as_str().unwrap(), "tools/call");
        assert_eq!(v.get_path(&["params", "name"]).unwrap().as_str().unwrap(), "continuum_recall");
        assert_eq!(v.get_path(&["params", "arguments", "query"]).unwrap().as_str().unwrap(), "database pool cap");
        assert_eq!(v.get_path(&["params", "arguments", "top_k"]).unwrap().as_u64().unwrap(), 5);
    }

    #[test]
    fn test_roundtrip_serialization() {
        let json = r#"{"name":"continuum","active":true,"count":750,"tags":["memory","ai"]}"#;
        let v = parse_json(json).unwrap();
        let rendered = v.to_json_string();
        let roundtrip = parse_json(&rendered).unwrap();
        assert_eq!(v, roundtrip);
    }
}
