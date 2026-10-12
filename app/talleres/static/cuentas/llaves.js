// Llaves de acceso: entrar con la huella, el patrón o el PIN de pantalla del celular (ver talleres/llaves.py).
// Sin librerías: el servidor manda las opciones de WebAuthn en JSON (base64url) y acá se pasan a bytes.
(function () {
  const aBytes = s => {
    const b = s.replace(/-/g, '+').replace(/_/g, '/');
    return Uint8Array.from(atob(b + '='.repeat((4 - b.length % 4) % 4)), c => c.charCodeAt(0)).buffer;
  };
  const aTexto = buf => btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const csrf = () => {
    const campo = document.querySelector('[name=csrfmiddlewaretoken]');
    return campo ? campo.value : ((document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '');
  };
  async function pedir(url, cuerpo) {
    const r = await fetch(url, {method: 'POST', credentials: 'same-origin', body: JSON.stringify(cuerpo || {}),
                                headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()}});
    const datos = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(datos.error || 'No se pudo. Probá de nuevo.');
    return datos;
  }
  const conSiguiente = (url, siguiente) => url + (siguiente ? '?next=' + encodeURIComponent(siguiente) : '');
  // Si la persona cancela o el celular no deja, el navegador tira NotAllowedError: no es un error nuestro.
  const mensaje = e => e && e.name === 'NotAllowedError' ? 'Se canceló.' : ((e && e.message) || 'No se pudo.');

  window.llaves = {
    disponible: () => !!(window.PublicKeyCredential && navigator.credentials && window.isSecureContext),
    mensaje,
    async crear(urls, siguiente) {
      const o = await pedir(urls.opciones);
      o.challenge = aBytes(o.challenge);
      o.user.id = aBytes(o.user.id);
      (o.excludeCredentials || []).forEach(c => { c.id = aBytes(c.id); });
      const c = await navigator.credentials.create({publicKey: o});
      return pedir(conSiguiente(urls.guardar, siguiente), {
        id: c.id, rawId: aTexto(c.rawId), type: c.type,
        response: {clientDataJSON: aTexto(c.response.clientDataJSON),
                   attestationObject: aTexto(c.response.attestationObject),
                   transports: c.response.getTransports ? c.response.getTransports() : []},
        clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {},
        authenticatorAttachment: c.authenticatorAttachment || undefined,
      });
    },
    async entrar(urls, usuario, siguiente) {
      const o = await pedir(urls.opciones, usuario ? {usuario} : {});
      o.challenge = aBytes(o.challenge);
      (o.allowCredentials || []).forEach(c => { c.id = aBytes(c.id); });
      const c = await navigator.credentials.get({publicKey: o});
      const r = c.response;
      return pedir(conSiguiente(urls.entrar, siguiente), {
        id: c.id, rawId: aTexto(c.rawId), type: c.type,
        response: {clientDataJSON: aTexto(r.clientDataJSON), authenticatorData: aTexto(r.authenticatorData),
                   signature: aTexto(r.signature), userHandle: r.userHandle ? aTexto(r.userHandle) : undefined},
        clientExtensionResults: {},
        authenticatorAttachment: c.authenticatorAttachment || undefined,
      });
    },
  };
})();
