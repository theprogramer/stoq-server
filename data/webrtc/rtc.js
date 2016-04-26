var io = require('socket.io-client'),
    xmlrpc = require('xmlrpc'),
    MultiRTC = require('./node_modules/components/utils/multi-rtc');

var socket;
var stoqServer = xmlrpc.createClient({host: 'localhost', port: 6970, path: '/XMLRPC'});
var clients = new MultiRTC({wrtc: require('wrtc')});
var host = process.env.STOQ_API_HOST || 'http://api.stoq.com.br';

/*
 * Socket.IO Hooks
 */

var connect = function() {
  console.info('trying to connect to ', host);
  socket = io.connect(host, {
    'force new connection': true,
    'max reconnection attempts': Infinity,
  });

  clients.signaller = socket;

  socket.on('connect', function() {
    console.info('connected to the signal server');
    stoqServer.methodCall('htsql_query', ["/parameter_data.filter(field_name = 'USER_HASH').field_value"],
      function(err, result) {
        var hash = JSON.parse(result).field_value[0];
        console.log('serving hash', hash);

        clients.metadata = {hash: hash};
        socket.emit('join', hash);
    });
  });

  socket.on('joined', function(id) {
    clients.add(id);
  });

  socket.on('signal', function(data) {
    clients.add(data.source, data.signal);
  });

  socket.on('disconnect', function() {
    console.info('disconnected to the signal server');
  });

  // Verifies if an error occurs when try to connect with the server. If the
  // server is off, retry the connection in 5 seconds (try until the server
  // stays online)
  socket.on('error', function(error) {
    if (error.match(/ECONNREFUSED/)) {
      console.error('connection failed: trying again in 5 seconds');
      setTimeout(connect, 5000);
    }
  });
};

connect();

/*
 * WebRTC Hooks
 */

var events = {
  /* Generic XMLRPC request to Stoq Server */
  xmlrpc: function(id, data) {
    stoqServer.methodCall(data.method, data.args, function(err, result) {
      // Send the error string if anything wrong happened
      if (err) {
        return clients.send({
          __response_id__: data.__response_id__,
          type: 'error',
          error: err.toString(),
        }, id);
      }

      // Send the response back to Stoq Web
      clients.send({
        __response_id__: data.__response_id__,
        type: 'xmlrpc',
        result: result,
      }, id);
    });
  },

  /* Executes a HTSQL query and send the result back to Stoq Web */
  htsql: function(id, data) {
    stoqServer.methodCall('htsql_query', [data.htsql], function(err, result) {
      // Send the error string if anything wrong happened
      if (err) {
        return clients.send({
          __response_id__: data.__response_id__,
          type: 'error',
          error: err.toString(),
        }, id);
      }

      clients.send({
        __response_id__: data.__response_id__,
        type: 'htsql',
        result: JSON.parse(result),
      }, id);
    });
  },
};

clients.on('connect', function(id) {
  console.log('connected to peer', id);
});

clients.on('data', function(id, data) {
  try {
    events[data.type](id, data);
  }
  catch(err) {
    console.error('Error: ', err);
    clients.send({
      __response_id__: data.__response_id__,
      type: 'error',
      error: err.toString(),
    });
  }
});

clients.on('disconnect', function(id) {
  console.log('disconnected to peer', id);
});
